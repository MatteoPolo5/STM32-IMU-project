"""Command line: analyse a log, capture from the serial port, or make a synthetic log."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import analysis as an
from .protocol import parse


def _plots(out: Path, log, sc, rate_hz, cpu_hz, tim) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    to_us = 1e6 / cpu_hz
    seqd = np.diff(log.seq.astype(np.int64)) == 1
    iv = an.wrapped_diff_u32(log.t_tick).astype(np.float64)[seqd] * to_us
    lat = an.wrapped_diff_u32_pairs(log.t_tick, log.t_done).astype(np.float64) * to_us
    ideal = 1e6 / rate_hz

    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
    ax[0].plot(iv - ideal, lw=0.4)
    ax[0].set(title="Sampling interval error", xlabel="sample", ylabel="interval - ideal [us]")
    ax[1].hist(iv - ideal, bins=80, log=True)
    ax[1].set(title="Jitter histogram", xlabel="interval - ideal [us]", ylabel="count (log)")
    fig.tight_layout(); fig.savefig(out / "timing_jitter.png", dpi=140); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
    ax[0].plot(lat, lw=0.4); ax[0].set(title="Tick -> DMA complete latency", xlabel="sample", ylabel="[us]")
    ax[1].hist(lat, bins=80, log=True); ax[1].set(title="Latency histogram", xlabel="[us]", ylabel="count (log)")
    fig.tight_layout(); fig.savefig(out / "latency.png", dpi=140); plt.close(fig)

    fig, ax = plt.subplots(2, 1, figsize=(11, 5), sharex=True)
    ax[0].plot(sc.t, sc.acc_g, lw=0.4); ax[0].set(ylabel="accel [g]"); ax[0].legend(["x", "y", "z"], ncol=3)
    ax[1].plot(sc.t, sc.gyro_dps, lw=0.4); ax[1].set(ylabel="gyro [deg/s]", xlabel="time [s]")
    fig.tight_layout(); fig.savefig(out / "imu_signals.png", dpi=140); plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 4))
    for i, name in enumerate("xyz"):
        tau, adev = an.allan_deviation(sc.gyro_dps[:, i], rate_hz)
        if tau.size:
            ax.loglog(tau, adev, label=f"gyro {name}")
    ax.set(title="Allan deviation (gyro)", xlabel="tau [s]", ylabel="sigma [deg/s]"); ax.grid(True, which="both", alpha=.3)
    ax.legend(); fig.tight_layout(); fig.savefig(out / "allan_gyro.png", dpi=140); plt.close(fig)


def cmd_analyze(a: argparse.Namespace) -> int:
    data = Path(a.logfile).read_bytes()
    log = parse(data)
    if len(log) < 10:
        print(f"error: only {len(log)} valid frames found in {a.logfile}", file=sys.stderr)
        return 1
    loss = an.loss_report(log)
    tim = an.timing_report(log, a.rate, a.cpu_hz)
    sc = an.scale(log, a.cpu_hz, a.accel_fs, a.gyro_fs)
    imu = an.imu_report(sc)
    report = {"file": str(a.logfile), "loss": asdict(loss), "timing": asdict(tim), "imu_static": asdict(imu)}

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, indent=2))
    if not a.no_plots:
        _plots(out, log, sc, a.rate, a.cpu_hz, tim)

    print(f"frames: {loss.frames_received} received / {loss.frames_expected} expected  "
          f"lost={loss.frames_lost} ({loss.loss_percent:.4f} %)  crc_errors={loss.crc_errors}  "
          f"out_of_order={loss.duplicate_or_reordered}")
    print(f"rate:   nominal {tim.rate_hz_nominal:.1f} Hz, measured {tim.rate_hz_measured:.3f} Hz")
    j = tim.jitter_us
    print(f"jitter: rms {j['rms']:.3f} us, peak-to-peak {j['peak_to_peak']:.3f} us, "
          f"max |err| {j['max_abs']:.3f} us (p99.9 {j['abs_p99.9']:.3f} us)")
    l = tim.latency_us
    print(f"latency tick->DMA done: mean {l['mean']:.1f} us, max {l['max']:.1f} us")
    print(f"static IMU: |a| = {imu.acc_norm_mean_g:.4f} g (err {imu.acc_norm_error_mg:+.1f} mg), "
          f"gyro bias = {imu.gyro_mean_dps} deg/s")
    print(f"written: {out}/summary.json" + ("" if a.no_plots else " + plots"))
    return 0


def cmd_capture(a: argparse.Namespace) -> int:
    import time

    import serial  # pyserial

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with serial.Serial(a.port, a.baud, timeout=0.2) as ser, open(out, "wb") as f:
        ser.reset_input_buffer()
        # Frames buffered in the ST-LINK / USB stack while nobody was reading arrive right after open
        # (seen as a seq jump in the first frames). Read and discard for a short warm-up.
        t_warm = time.time() + a.warmup
        while time.time() < t_warm:
            ser.read(4096)
        t_end = time.time() + a.duration
        print(f"capturing {a.duration:.0f} s from {a.port} @ {a.baud} -> {out}  (Ctrl-C to stop early)")
        try:
            while time.time() < t_end:
                chunk = ser.read(4096)
                f.write(chunk); total += len(chunk)
        except KeyboardInterrupt:
            pass
    print(f"{total} bytes written ({total / 32:.0f} frames)")
    return 0


def cmd_simulate(a: argparse.Namespace) -> int:
    from .simulate import simulate

    data = simulate(a.duration, a.rate, a.cpu_hz, drop_prob=a.drop, corrupt_prob=a.corrupt, seed=a.seed)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(data)
    print(f"synthetic log written to {a.out} ({len(data)} bytes) - NOT real data")
    return 0


def cmd_stats(a: argparse.Namespace) -> int:
    from . import stats as st

    if a.from_text:
        s = st.decode(st.parse_mdw(Path(a.from_text).read_text()), a.cpu_hz)
    else:
        s = st.read_from_target(Path(a.elf), cpu_hz=a.cpu_hz)
    for k in st.FIELDS:
        print(f"{k:>20}: {s[k]}")
    print(f"{'max_latency_us':>20}: {s['max_latency_us']:.1f}")
    for line in st.verdict(s):
        print(line)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="imu_daq", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("analyze", help="analyse a captured .bin log")
    s.add_argument("logfile")
    s.add_argument("--rate", type=float, default=1000.0, help="nominal sample rate [Hz] (firmware SAMPLE_RATE_HZ)")
    s.add_argument("--cpu-hz", type=float, default=84e6)
    s.add_argument("--accel-fs", type=int, default=0, choices=range(4), help="MPU_ACCEL_FS_SEL used in the firmware")
    s.add_argument("--gyro-fs", type=int, default=0, choices=range(4), help="MPU_GYRO_FS_SEL used in the firmware")
    s.add_argument("--out", default="results/latest")
    s.add_argument("--no-plots", action="store_true")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("capture", help="record the serial stream to a file")
    s.add_argument("--port", required=True, help="e.g. /dev/ttyACM0, COM5, /dev/tty.usbmodem1303")
    s.add_argument("--baud", type=int, default=460800)
    s.add_argument("--duration", type=float, default=600.0, help="seconds")
    s.add_argument("--out", default="data/capture.bin")
    s.add_argument("--warmup", type=float, default=1.0, help="seconds of data discarded after opening the port")
    s.set_defaults(fn=cmd_capture)

    s = sub.add_parser("simulate", help="write a synthetic log (for testing the tools)")
    s.add_argument("--duration", type=float, default=10.0)
    s.add_argument("--rate", type=float, default=1000.0)
    s.add_argument("--cpu-hz", type=float, default=84e6)
    s.add_argument("--drop", type=float, default=0.0, help="probability of a lost frame")
    s.add_argument("--corrupt", type=float, default=0.0, help="probability of a corrupted frame")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", default="data/synthetic.bin")
    s.set_defaults(fn=cmd_simulate)

    s = sub.add_parser("stats", help="read the firmware's internal counters over SWD (needs openocd)")
    s.add_argument("--elf", default="../build/firmware/firmware/imu_daq.elf")
    s.add_argument("--from-text", help="decode saved OpenOCD 'mdw' output instead of reading the board")
    s.add_argument("--cpu-hz", type=float, default=84e6)
    s.set_defaults(fn=cmd_stats)

    a = p.parse_args(argv)
    return a.fn(a)