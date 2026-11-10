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
    sc_all = an.scale(log, a.cpu_hz, a.accel_fs, a.gyro_fs)
    sc = sc_all
    if a.trim > 0:  # static statistics and Allan without the first/last seconds (handling of the board)
        keep = (sc_all.t >= a.trim) & (sc_all.t <= sc_all.t[-1] - a.trim)
        sc = an.Scaled(t=sc_all.t[keep], acc_g=sc_all.acc_g[keep], gyro_dps=sc_all.gyro_dps[keep], temp_c=sc_all.temp_c[keep])
    imu = an.imu_report(sc)
    report = {"file": str(a.logfile), "loss": asdict(loss), "timing": asdict(tim), "imu_static": asdict(imu)}
    allan = {}
    for i, name in enumerate("xyz"):
        tau, adev = an.allan_deviation(sc.gyro_dps[:, i], a.rate)
        allan[name] = an.allan_summary(tau, adev)
    report["allan_gyro"] = allan

    side = Path(str(a.logfile) + ".times.csv")
    host = None
    if side.exists():
        tt = np.loadtxt(side, delimiter=",", skiprows=1)
        host = an.host_rate(tt[:, 0], tt[:, 1])
        report["host_rate"] = host

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(report, indent=2))
    if not a.no_plots:
        _plots(out, log, sc, a.rate, a.cpu_hz, tim)

    print(f"frames: {loss.frames_received} received / {loss.frames_expected} expected  "
          f"lost={loss.frames_lost} ({loss.loss_percent:.4f} %)  crc_errors={loss.crc_errors}  "
          f"out_of_order={loss.duplicate_or_reordered}")
    print(f"rate:   nominal {tim.rate_hz_nominal:.1f} Hz, measured {tim.rate_hz_measured:.3f} Hz")
    if host:
        r = host["rate_hz"]
        print(f"host:   {r:.3f} frames/s over {host['duration_s']:.1f} s ({(r / a.rate - 1) * 1e6:+.0f} ppm vs nominal; "
              f"halves {host['rate_hz_first_half']:.3f} / {host['rate_hz_second_half']:.3f})")
    j = tim.jitter_us
    print(f"jitter: rms {j['rms']:.3f} us, peak-to-peak {j['peak_to_peak']:.3f} us, "
          f"max |err| {j['max_abs']:.3f} us (p99.9 {j['abs_p99.9']:.3f} us)")
    l = tim.latency_us
    print(f"latency tick->DMA done: mean {l['mean']:.1f} us, max {l['max']:.1f} us")
    print(f"static IMU: |a| = {imu.acc_norm_mean_g:.4f} g (err {imu.acc_norm_error_mg:+.1f} mg), "
          f"gyro bias = {imu.gyro_mean_dps} deg/s")
    for name in "xyz":
        g = allan[name]
        if g["arw_deg_per_sqrt_h"] is None:
            print(f"gyro {name} Allan: capture too short for tau = 1 s")
            continue
        bi = (f"bias instability {g['bias_instability_deg_per_h']:.1f} deg/h at tau {g['bias_instability_tau_s']:.1f} s"
              if g["bias_instability_observed"] else
              f"bias instability not observed (tau <= {g['tau_max_s']:.0f} s; needs a floor and >= 20 averages at the minimum)")
        sl = f"{g['slope_at_1s']:+.2f}" if g["slope_at_1s"] is not None else "n/a"
        print(f"gyro {name} Allan: ARW {g['arw_deg_per_sqrt_h']:.3f} deg/sqrt(h) (slope at 1 s {sl}), {bi}")
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
        stamps = []  # (host monotonic time, cumulative bytes) for every non-empty read
        try:
            while time.time() < t_end:
                chunk = ser.read(4096)
                f.write(chunk); total += len(chunk)
                if chunk:
                    stamps.append((time.monotonic(), total))
        except KeyboardInterrupt:
            pass
    Path(str(out) + ".times.csv").write_text(
        "t_s,bytes\n" + "".join(f"{t:.6f},{b}\n" for t, b in stamps))
    print(f"{total} bytes written ({total / 32:.0f} frames)")
    return 0


def _static_means(path: str, a: argparse.Namespace) -> dict:
    log = parse(Path(path).read_bytes())
    if len(log) < 100:
        raise SystemExit(f"error: only {len(log)} valid frames in {path}")
    sc = an.scale(log, a.cpu_hz, a.accel_fs, a.gyro_fs)
    keep = (sc.t >= a.trim) & (sc.t <= sc.t[-1] - a.trim)
    if keep.sum() < 100:
        raise SystemExit(f"error: {path} is too short for --trim {a.trim}")
    return {"n": int(keep.sum()), "acc": sc.acc_g[keep].mean(axis=0), "acc_std_mg": sc.acc_g[keep].std(axis=0) * 1e3,
            "gyro": sc.gyro_dps[keep].mean(axis=0), "temp": float(sc.temp_c[keep].mean()), "acc_all": sc.acc_g[keep]}


def cmd_calibrate(a: argparse.Namespace) -> int:
    from . import calibration as cal

    files = {"+x": a.xp, "-x": a.xn, "+y": a.yp, "-y": a.yn, "+z": a.zp, "-z": a.zn}
    data = {pos: _static_means(f, a) for pos, f in files.items()}
    means = {pos: d["acc"] for pos, d in data.items()}
    try:
        fit = cal.fit_accel_six_position(means)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    warns = cal.tilt_warnings(means)
    gyro = np.array([d["gyro"] for d in data.values()])
    gyro_bias = gyro.mean(axis=0)
    gyro_spread = gyro.max(axis=0) - gyro.min(axis=0)

    rows = {}
    for pos, d in data.items():
        rows[pos] = {"norm_error_mg_before": cal.norm_error_mg(d["acc_all"]),
                     "norm_error_mg_after": cal.norm_error_mg(cal.apply_accel(d["acc_all"], fit)),
                     "temp_c": d["temp"], "gyro_dps": d["gyro"].round(5).tolist()}
    held = {}
    for f in a.validate or []:
        d = _static_means(f, a)
        held[f] = {"norm_error_mg_before": cal.norm_error_mg(d["acc_all"]),
                   "norm_error_mg_after": cal.norm_error_mg(cal.apply_accel(d["acc_all"], fit)),
                   "acc_mean_g": d["acc"].round(5).tolist(), "temp_c": d["temp"]}

    result = {"model": "accel: scale*(raw-bias), six-position, diagonal; gyro: bias only",
              "accel_bias_g": fit.bias_g.round(6).tolist(), "accel_scale": fit.scale.round(6).tolist(),
              "gyro_bias_dps": gyro_bias.round(5).tolist(), "gyro_bias_spread_dps": gyro_spread.round(5).tolist(),
              "temp_c_mean": float(np.mean([d["temp"] for d in data.values()])),
              "fit_positions": rows, "held_out": held, "warnings": warns, "files": {**files, "validate": a.validate or []}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2))

    print(f"accel bias [g]:   {fit.bias_g.round(4).tolist()}")
    print(f"accel scale:      {fit.scale.round(5).tolist()}   (1.0 = nominal sensitivity)")
    print(f"gyro bias [deg/s]: {gyro_bias.round(4).tolist()}   spread between the six positions {gyro_spread.round(4).tolist()}")
    for pos, r in rows.items():
        print(f"  {pos}: |a| error {r['norm_error_mg_before']:+.1f} mg -> {r['norm_error_mg_after']:+.1f} mg   (in the fit)")
    for f, r in held.items():
        print(f"  held out {Path(f).name}: |a| error {r['norm_error_mg_before']:+.1f} mg -> {r['norm_error_mg_after']:+.1f} mg")
    for w in warns:
        print(f"warning: {w}")
    print(f"written: {a.out}")
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
    s.add_argument("--trim", type=float, default=0.0,
                   help="seconds dropped at the start and end for the static IMU statistics and the Allan deviation")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("calibrate", help="static calibration from six captures (+-x, +-y, +-z up) and held-out checks")
    for k, h in (("xp", "+x up"), ("xn", "-x up (x down)"), ("yp", "+y up"), ("yn", "-y up (y down)"),
                 ("zp", "+z up (flat, component side up)"), ("zn", "-z up (flat, upside down)")):
        s.add_argument("--" + k, required=True, help="capture with the board at rest, " + h)
    s.add_argument("--validate", nargs="*", help="static captures in other orientations, NOT used in the fit")
    s.add_argument("--trim", type=float, default=2.0, help="seconds dropped at the start and end of each capture")
    s.add_argument("--accel-fs", type=int, default=0)
    s.add_argument("--gyro-fs", type=int, default=0)
    s.add_argument("--cpu-hz", type=float, default=84e6)
    s.add_argument("--out", default="results/calibration.json")
    s.set_defaults(fn=cmd_calibrate)

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
