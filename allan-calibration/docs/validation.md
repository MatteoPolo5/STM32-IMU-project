# Validation plan and results

The goal of this project is not "it prints IMU data" but "it samples at a known rate, and I can prove it".
Every test has a pass criterion and the command that produces the number.

## Tests and status

| ID | What | How | Pass criterion | Status |
|---|---|---|---|---|
| T1 | Sensor bring-up | banner shows `who_am_i=0x68` | present | **Pass** (2026-10-28) |
| T2 | No lost samples, end to end | 10 min capture at 1 kHz, `analyze` | `frames_lost == 0`, `crc_errors == 0` | **Pass on native Linux**: 600 s, 608 511 frames, 0 lost, 0 CRC errors with the fixed `capture` (linux_10min_b, see run log 2026-11-02). Not met on the first (virtual-machine USB) path: 79 lost (0.13 %) in 60 s |
| T2b | No lost samples, firmware side | internal counters via `tools/read_stats.py` | overruns = ring overflows = I2C errors = watchdog aborts = 0, `frames_sent == ticks` | **Pass**: 958 398 samples, all counters 0 |
| T3 | Absolute sampling rate | compare sample count with an independent time reference | within 100 ppm (HSE) | **Partly verified**: HSI build ran about +1.3 % fast (1013-1015 frames/s); HSE build gives 60 032 frames in 60 s (+0.05 %, inside the host timing uncertainty of about 0.2 %). Repeated 2026-11-04: +0.05 % (60 s), +0.01 % (600 s). Not yet shown within 100 ppm, see run logs 2026-11-03 and 2026-11-04 |
| T4 | ISR-entry jitter (from log) | `jitter_us` in `summary.json` | report rms, peak-to-peak, max | **Recorded** (table below) |
| T5 | Jitter, independent check | logic analyzer on a pin toggled in the TIM2 ISR | compare with T4 | Not done |
| T6 | Acquisition latency | `latency_us` | max < 80 % of the period | **Pass**: 388.7 µs max (39 % of 1 ms) |
| T7 | Static IMU sanity | board still on the table | see "Criterion revision" below | **Pass** (revised criterion) |
| T8 | Fault injection: stalled main loop | debug build with `hw::delay_ms(200)` added to `daq::poll()` | `ring_overflows` increases, gaps visible in `seq`, stream recovers | Not done |
| T9 | Fault injection: I2C | disconnect SDA for 1 s during streaming, reconnect | `i2c_errors` / `watchdog_aborts` increase, streaming resumes by itself | **Pass on resume and loss accounting** (2026-11-04); `i2c_errors` / `watchdog_aborts` counters not read |
| T10 | Rate sweep | build with 200 / 500 / 1000 Hz | table below | **Done** (200 / 500 / 1000 Hz, 0 lost in every run, see table below) |
| T11 | Capture path independence | same 60 s capture on a native Linux PC (no virtual machine, no USB forwarding) | compare gap statistics with the first runs | **Done**: no loss on native Linux (60 s and 600 s), so the losses were not reproduced without the virtual-machine path. Consistent with that path being the cause, not proof of it (one board, one PC, two sessions) |
| T12 | Gyro noise (Allan deviation) | 10 min static capture, `analyze` prints ARW and bias instability per axis | report values with the observed/not-observed flags; no pass/fail (compare with the datasheet value, to be looked up) | Not done |
| T13 | Static calibration | six-position captures + 1 held-out orientation, `calibrate` | held-out abs(a) error after calibration below 10 mg (before: about +60 to +70 mg); gyro bias spread over the six positions below 0.05 deg/s | Not done |

### Criterion revision (T7)

The original criterion was `abs(norm(a) - 1 g) < 30 mg`. That number was a guess made before any
measurement. The first runs gave +69 mg and +73 mg, which is not unusual for an uncalibrated MEMS accelerometer
(initial offset and sensitivity tolerances are specified in the MPU-6000/6050 datasheet; check the exact values there
before quoting them). The criterion was therefore replaced, *after* seeing the data, by:

* **repeatability**: norm error differs by less than 5 mg and gyro bias by less than 0.05 deg/s between runs;
* absolute accuracy is addressed by a calibration step (see roadmap), not by this test.

Result: run 1 vs run 2 differ by 3.5 mg (norm) and by 0.003 / 0.013 / 0.003 deg/s (gyro bias) -> pass.

## Allan deviation and calibration (T12, T13)

Criteria are fixed here before the measurements.

**T12.** Board flat and still, 10 min at 1 kHz, no touching. `python -m imu_daq analyze` prints, for each gyro axis, the
angle random walk (curve value at tau = 1 s, valid only if the slope there is about -0.5) and the bias instability
(curve minimum / 0.664, valid only if the curve has stopped falling before the longest tau). With 10 min of data the
longest tau is 200 s; a flat bottom may not be visible, in which case only an upper bound is stated.

**T13.** Six captures of about 30 s each with the board resting on a table with one axis pointing up or down in turn
(+x, -x, +y, -y, +z, -z; the board must not move during a capture; a book or a box corner helps to hold the edges level),
plus one capture in a different orientation (for example resting on an edge at about 45 degrees) that is **not** used
in the fit.

```bash
cd tools
python -m imu_daq capture --port /dev/ttyACM0 --duration 30 --out ../data/cal_zp.bin    # repeat for the other five
python -m imu_daq calibrate --xp ../data/cal_xp.bin --xn ../data/cal_xn.bin --yp ../data/cal_yp.bin \
    --yn ../data/cal_yn.bin --zp ../data/cal_zp.bin --zn ../data/cal_zn.bin \
    --validate ../data/cal_held.bin --out ../results/calibration.json
```

The model is offset + per-axis sensitivity for the accelerometer and offset for the gyroscope. Axis misalignment and
gyro sensitivity are not calibrated (the latter needs a known rotation), and the temperature dependence is not modelled:
the calibration is valid near the temperature at which it was made (recorded in the JSON).

## How to reproduce

```bash
cd tools
python -m imu_daq capture --port /dev/ttyACM0 --duration 600 --out ../data/run_1khz.bin
python -m imu_daq analyze ../data/run_1khz.bin --rate 1000 --out ../results/run_1khz
# MATLAB / Octave
#   r = analyze_log('data/run_1khz.bin', 1000);

# Firmware-side counters (board connected, no other debugger session open):
cd ..
python tools/read_stats.py                  # decodes daq::g_stats read through OpenOCD, CPU keeps running
```

`analyze` writes `summary.json` and plots (`timing_jitter.png`, `latency.png`, `imu_signals.png`, `allan_gyro.png`).

Where the losses are (gap positions and sizes, firmware drop counter):

```bash
cd tools
python -I - <<'EOF'
import sys; sys.path.insert(0, '.')
import numpy as np
from imu_daq.protocol import parse
L = parse(open('../data/run_1khz.bin', 'rb').read())
d = np.diff(L.seq.astype(np.int64)); idx = np.flatnonzero(d > 1)
print("gaps:", idx.size, "sizes:", sorted(set((d[idx] - 1).tolist())))
print("at (s):", np.round((L.seq[idx] - L.seq[0]) / 1000, 2).tolist()[:40])
print("firmware dropped counter (last):", int(L.dropped[-1]))
EOF
```

## Run log

### 2026-10-28: first hardware runs

**Setup.** NUCLEO-F446RE (ST-LINK V2J33M25), GY-521 (MPU6050, AD0 = GND, address 0x68). Firmware 0.1.0 plus the I2C
diagnostics patch, arm-none-eabi-gcc 13.2.1, Release. 1 kHz, I2C 400 kHz, 460800 baud, HSI clock. Host: Windows laptop,
Ubuntu 24.04 in a virtual machine, ST-LINK USB forwarded into it, capture with pyserial. IMU resting on the table (not guaranteed
flat: the first 19-sample snapshot had `ay` = 0.37 g).

**Results.**

| Run | Wall time | Frames received | Seq range | Lost | CRC errors | Jitter rms | Jitter p-p | Max abs err | Latency mean / max |
|---|---|---|---|---|---|---|---|---|---|
| prova1 | 10 s | 9727 | 9727 | 0 | 0 | 0.004 µs | 0.036 µs | 0.024 µs | 388.6 / 388.7 µs |
| prova2 | 60 s | 60 793 | 60 872 | 79 (0.130 %) | 6 | 0.004 µs | 0.048 µs | 0.024 µs | 388.6 / 388.7 µs |

Jitter is the variation of the *timer-interrupt entry* time (CPU almost idle), not an end-to-end sampling jitter.

Static IMU (uncalibrated):

| Run | abs(a) [g] | Error [mg] | Gyro bias [deg/s] |
|---|---|---|---|
| prova1 | 1.0694 | +69.4 | [-0.994, -1.551, 0.409] |
| prova2 | 1.0729 | +72.9 | [-0.991, -1.564, 0.406] |

**Gap analysis, prova2.** 10 gaps of 1, 3, 4, 6, 11, 17 and 25 frames, at about 7.31 s, 8.00 s, 8.02 s and seven
within 59.00-59.48 s. The firmware's own `dropped` counter was 0 in every frame.

**Firmware-side counters** (OpenOCD `mdw` at `daq::g_stats`, about 16 min after reset, covering both runs):

| ticks | completed | overruns | ring_overflows | i2c_errors | watchdog_aborts | frames_sent | max latency |
|---|---|---|---|---|---|---|---|
| 958 398 | 958 398 | 0 | 0 | 0 | 0 | 958 398 | 32 647 cycles = 388.7 µs |

**Interpretation (what is established, what is not).**
* Established: in 958 398 samples the firmware acquired every sample and handed every frame to the UART DMA, with no
  I2C error, overrun or ring overflow.
* Established: the 79 missing frames were lost after the UART DMA hand-off.
* *Not* established: where. Candidates: ST-LINK virtual COM port buffer, USB, USB forwarding into the virtual machine, the host
  reading loop. The burst-like pattern (clusters of small gaps) is consistent with host-side read stalls, but this is
  a hypothesis. T11 (native Linux capture) is the test that separates the virtual-machine path from the rest.

**Open issues.**
1. *Wall clock vs sample count.* The 10 s capture contains 9.727 s of samples; the 60 s capture contains 60.872 s.
   Written at the time as unresolved. Later runs (2026-11-02 and 2026-11-03) explain the 60 s case: with the HSI the
   MCU runs about 1.3-1.5 % fast, and with the HSE it does not. The 10 s case (a deficit of 2.7 %) is not explained by
   this; it was captured on the first path and is not analysed further.
2. T2 (zero loss end to end) is not met on the first (virtual-machine) path; met later on native Linux.

**Bring-up notes (useful if it happens again).**
* First symptom: `FATAL: MPU6050 not responding`. The firmware diagnostics reported
  `failed at 'R:addr+W ACK' SR1=0x400 (AF) SR2=0x3 SCL=1 SDA=1` and an address scan with no answers, i.e. the master worked
  and nobody acknowledged. An independent Arduino Uno I2C scanner also found nothing, which placed the fault on the
  breakout. Cause: the SCL header pin was not making contact on the breakout. After fixing it, `who_am_i=0x68`.
* Lesson: a voltage read on a header pin that is wired to the MCU says nothing about the solder joint on the other side.

### 2026-11-02: native Linux capture (T11)

**Setup.** Same board, sensor and firmware as above. Host: HP EliteBook 840 G7, Ubuntu 20.04.6, Python 3.8.10,
numpy 1.17.4, `/dev/ttyACM0` directly (no virtual machine, no USB forwarding).

**Results.**

| Run | Wall time | Frames received | Seq range (contiguous part) | Lost | CRC errors | Jitter rms | Latency mean / max |
|---|---|---|---|---|---|---|---|
| linux1 | 60 s | 60 928 | 60 928 | 0 | 0 | not recorded | not recorded |
| linux_10min | 600.19 s | 608 127 (11 + 608 116) | 608 116 after the start jump | 0 after the jump (see below) | 0 | 0.004 µs | 388.6 / 388.7 µs |

linux_10min, static IMU: abs(a) = 1.0665 g (+66.5 mg), gyro bias [-1.01768, -1.52198, 0.34553] deg/s, temperature 23.2 C.

**The "33.79 % lost" reported by `analyze` for linux_10min is not a loss during the capture.** `analyze` computes
`lost = (last seq - first seq + 1) - received`. The sequence differences are: 608 125 steps of +1 and exactly one step of
+310 362, located at frame #10, i.e. 11 frames after the start of the file (seq 84745 .. 84755, then 395117). After the
jump the 608 116 frames are strictly consecutive (395117 .. 1003232). The firmware `dropped` counter is 0 in the first
and the last frame.

* Established: there is a single discontinuity, at the very beginning of the file; no gap anywhere in the remaining
  600 s; 0 CRC errors.
* Cause (reproduced, see linux3/linux4 below): the first frames are stale data that sat in the ST-LINK / USB buffers
  while nobody was reading (the firmware keeps streaming). `reset_input_buffer()` only clears the host buffer. The
  jump equals the time the board ran unread.

**Reproduction of the start jump (A/B).** Same PC, board left running unread for some minutes before each capture.

| Run | Option | Frames | Frames before the jump | Jump |
|---|---|---|---|---|
| linux4 | `--warmup 0` (old behaviour) | 20 351 | 10 | 84 527 ticks (about 84 s) |
| linux3 | `--warmup 1` (new default) | 60 800 | no jump | none, 0 lost, 0 CRC errors |

The jump is present without the warm-up and absent with it. Limits: one run per arm, and the idle time before linux3
was not measured. Fix: `capture` now reads and discards the first second (`--warmup`, default 1 s).

**Clean 10 min run with the fix (linux_10min_b).** 608 511 frames received / 608 511 expected, lost 0, CRC errors 0,
out of order 0. Jitter rms 0.004 µs, p-p 0.048 µs, max |err| 0.024 µs; latency 388.6 / 388.7 µs. Static IMU:
|a| = 1.0623 g (+62.3 mg), gyro bias [-1.00551, -1.51608, 0.38757] deg/s. This meets T2 on native Linux.
Rate: 608 511 frames in about 600 s = about 1014 frames/s (+1.4 %), consistent with the earlier native runs; T3 still open.

**T7 across all sessions.** |a| error: +69.4, +72.9 (first two runs, virtual machine), +66.5, +66.8, +62.3 mg (native Linux); gyro bias z:
0.409, 0.406, 0.346, 0.274, 0.388 deg/s. Within the same day and setup the 5 mg / 0.05 deg/s criterion holds; across
the whole set it does not (spread 10.6 mg and 0.135 deg/s). The sensor was not re-placed identically each time and
temperature was not controlled, so the cause is not identified. The criterion is not loosened again.

**Wall clock vs sample count (T3).** linux1: 60 928 frames in about 60 s; linux_10min: 608 116 live frames in 600.19 s,
about 1013.2 frames/s, i.e. about 1.3 % more than the nominal 1000 Hz. The two windows are consistent with each other
(the 60 s window has larger start/stop uncertainty). The MCU runs from the HSI oscillator, whose tolerance is of
this order, so a fast HSI is a candidate explanation. Not established: it could also be the host timing. T3 stays open
until the same capture is repeated with the HSE (done 2026-11-03, see below).

**Interpretation.**
* Established: on this PC, 10 minutes of streaming at 1 kHz arrive without gaps and without CRC errors.
* Not established: that the virtual-machine USB path caused the earlier 79 lost frames (see T11 row).
* Tool issue: `analyze` hides the structure of the loss behind one percentage. It should report the number of gaps,
  their sizes and positions, and flag a discontinuity in the first frames.

### 2026-11-03: HSE clock source (T3)

**Change.** Firmware rebuilt with `-DUSE_HSE_BYPASS=ON`, which is now the default (8 MHz MCO of the ST-LINK as PLL source). Banner confirms the
source: `E3-DAQ fw=0.1.0 rate=1000Hz i2c=400kHz baud=460800 clk=HSE who_am_i=0x68`. Host as on 2026-11-02, fixed `capture`.
Build on Ubuntu 20.04: CMake >= 3.21 from pip, gcc-arm-none-eabi 9.2.1, OpenOCD 0.10 (flash with
`interface/stlink-v2-1.cfg`, see `OPENOCD_INTERFACE`), linker script without `(READONLY)` (binutils < 2.35).

**Result (hse1, 60 s).** 60 032 frames received / 60 032 expected, lost 0, CRC errors 0, out of order 0. Jitter rms
0.004 µs, p-p 0.036 µs, latency 388.6 / 388.6 µs. Static IMU: |a| = 1.0678 g (+67.8 mg), gyro bias
[-1.02377, -1.49142, 0.34633] deg/s.

| Clock | Frames in the 60 s window | Rate |
|---|---|---|
| HSI | 60 800 - 60 928 | about 1013-1015 /s (+1.3 to +1.5 %) |
| HSE | 60 032 | about 1000.5 /s (+0.05 %) |

* Established: the +1.3 % excess disappears when the PLL is fed by the HSE; it was the HSI, not the host or the protocol.
* Not established: accuracy at the 100 ppm level. The capture window is `time.time()` based and `read()` returns in
  chunks of up to 4096 bytes (about 0.13 s of data), so the window is known to roughly 0.2 %. One run only.
  To reach 100 ppm: record the host time of the first and last frame and capture at least 10 min.
* The ST-LINK MCO accuracy was not measured.

### 2026-11-04: reproducibility (3 x 60 s, 1 x 600 s)

**Setup.** Same board, sensor and host as 2026-11-03; firmware built with the default (HSE) configuration, board left still
and powered between runs. The firmware banner was not recorded in this session. Criteria written before the runs: 0 lost,
0 CRC errors, latency max 388-390 us, frame count within +-0.3 % of nominal.

| Run | Window | Frames | Lost | CRC | Jitter rms / p-p | Latency mean / max | abs(a) [g] (error) | Gyro bias [deg/s] |
|---|---|---|---|---|---|---|---|---|
| rep60_1 | 60 s | 60 031 | 0 | 0 | 0.004 / 0.048 us | 388.6 / 388.6 us | 1.0705 (+70.5 mg) | [-1.00538, -1.54665, 0.22743] |
| rep60_2 | 60 s | 60 031 | 0 | 0 | 0.004 / 0.048 us | 388.6 / 388.6 us | 1.0699 (+69.9 mg) | [-1.0157, -1.54193, 0.23788] |
| rep60_3 | 60 s | 60 031 | 0 | 0 | 0.004 / 0.048 us | 388.6 / 388.6 us | 1.0696 (+69.6 mg) | [-1.01454, -1.54423, 0.24195] |
| rep600 | 600 s | 600 063 | 0 | 0 | 0.004 / 0.048 us | 388.6 / 388.6 us | 1.0689 (+68.9 mg) | [-1.0022, -1.54017, 0.26108] |

**Result against the criteria.** All four runs meet them: no lost frames, no CRC errors, latency 388.6 us, frame counts
+0.05 % (60 s) and +0.01 % (600 s) from nominal. Timing numbers are identical across runs.

**Limits of the rate figure.** `capture` reads in chunks of 4096 bytes (128 frames, 0.128 s) and stops at a chunk
boundary: every run wrote an exact multiple of 4096 bytes (469 chunks for 60 s, 4688 for 600 s). The window is therefore
quantised to 0.128 s, i.e. about 0.2 % at 60 s and about 0.02 % (210 ppm) at 600 s. The excess of 63 frames over 600 s
(105 ppm) is smaller than that uncertainty, so it is consistent with no clock error, but it does not demonstrate 100 ppm.
The three identical 60 s frame counts come from this quantisation and are not independent evidence of the rate.

**Static IMU repeatability.** Within this session the four runs differ by 1.6 mg in the norm error and by 0.0135 / 0.0065 /
0.034 deg/s in the gyro bias (x / y / z): within the 5 mg and 0.05 deg/s criterion. Across all native-Linux sessions the
norm error spans +62.3 to +70.5 mg and the z bias 0.227 to 0.409 deg/s, so the cross-session spread remains above the
criterion for the z bias. Cause not identified (temperature was not recorded; sensor warm-up is a possibility, not tested).

### 2026-11-04: rate sweep (T10) and a start-up anomaly

**Sweep.** Builds with `-DSAMPLE_RATE_HZ=200` and `=500` (HSE, default otherwise), flashed with OpenOCD, 60 s captures on
native Linux, `analyze --rate N`. Banner of the 200 Hz build: `E3-DAQ fw=3eeb0dd rate=200Hz i2c=400kHz baud=460800 clk=HSE
who_am_i=0x68`; the banner of the 500 Hz build was not recorded.

| Rate | Frames in 60 s | Rate vs nominal | Lost | CRC | Jitter rms / p-p | Latency mean / max | abs(a) [g] |
|---|---|---|---|---|---|---|---|
| 200 Hz | 12 014 | +0.12 % | 0 | 0 | 0.001 / 0.024 us | 388.5 / 388.5 us | 1.0683 |
| 500 Hz | 30 036 | +0.12 % | 0 | 0 | 0.004 / 0.036 us | 388.6 / 388.6 us | 1.0685 |

Rate vs nominal is within the capture-window uncertainty (about 0.3 %). The acquisition latency does not depend on the
sampling rate: it is the I2C transaction time at 400 kHz (estimate 387.5 us). The jitter figures are small at all three
rates; their differences were not investigated and should not be over-read.

**Anomaly: sensor not answering after a flash.** Observed twice after programming with OpenOCD:
1. 2026-11-03, after flashing the HSE build: banner `FATAL: MPU6050 not responding`; worked after checking the wiring and
   re-powering the board (the exact action that fixed it was not recorded).
2. 2026-11-04, after flashing the 200 Hz build: the first 60 s capture contains only the repeated `FATAL` message (8 520
   bytes, 0 valid frames). After pressing RESET, the banner was normal (`who_am_i=0x68`) and the capture was clean.
   The 500 Hz flash did not show it.

Established: the firmware and the sensor work after a reset; the fault is intermittent and clears with a reset or a
power cycle. **Repeat test (2026-11-04): 5 flashes in a row of the 1000 Hz build, each followed by a 3 s read: 5 of 5 OK, no
`FATAL`.** The anomaly was not reproduced; with this few trials it is not excluded either. Not established: the cause. Candidates: an intermittent wire contact (as in the first bring-up), or the
flash reset interrupting an I2C transfer and leaving the sensor holding SDA low. Open: if it happens again, note whether a plain RESET clears it
(wire contact more likely) or only a power cycle does. I2C bus recovery (9 SCL pulses before initialisation) is a cheap
robustness measure but was not added, since the failure was not reproduced.

### 2026-11-04: SDA disconnected during streaming (T9)

**Setup.** 1000 Hz, HSE build (default), native Linux host, 40 s capture (`t9_sda.bin`). At about 15 s the SDA wire (D14)
was pulled by hand and reconnected; the real duration of the disconnection was not timed by hand.

**Results.**
* Frames received 37 053, one gap of 2 995 samples after 15 165 frames, then 21 888 consecutive frames to the end of the
  capture. No other gap, 0 CRC errors, 11 non-frame bytes (a partial frame at the start of the file, after the warm-up).
* The firmware `dropped` counter goes from 0 to 2 995, equal to the gap in `seq`: the firmware accounted for every
  sample it could not acquire.
* Duration of the gap from the DWT timestamps of the frames around it: 2.996 s, consistent with 2 995 lost ticks at 1 kHz
  (both come from the same MCU clock, so this checks consistency, not the absolute rate).
* Samples around the gap (seq 476300, 476301 | 479297, 479298, 479299): accelerations 1.02-1.20 g before, 1.07 g after;
  no saturated or all-zero values. The gyro reads 45-47 deg/s before the gap and about -2.8 deg/s after it. My reading is
  that the board was being handled by hand when the wire was pulled (not measured); it is not a sign of corrupted data.

**Interpretation.**
* Established: after a loss of the I2C line lasting about 3 s the firmware resumed streaming by itself, without reset, and
  the loss is fully accounted for by `dropped`; no frames with corrupted content were emitted around the gap.
* Not established: how many I2C errors / watchdog aborts the firmware counted (`read_stats.py` was not available on this
  host), and whether a shorter or longer interruption, or one in the middle of a transfer, behaves the same. One
  repetition only.

### Template for the next runs

Copy this block for each new run and fill it with measured values.

```
### YYYY-MM-DD: <what changed>
Setup: board / sensor / firmware commit (git describe) / toolchain / host / capture path
Command: ...
Result row: frames received, seq range, lost, CRC errors, jitter rms/p-p/max, latency mean/max
Firmware counters: python tools/read_stats.py
Interpretation: what is established, what is not
```

## Results (rate sweep, to be filled in)

| Rate | Duration | Frames | Lost | CRC errors | Jitter rms [µs] | Jitter p-p [µs] | Latency max [µs] |
|---|---|---|---|---|---|---|---|
| 200 Hz | 60 s (native Linux) | 12 014 | 0 | 0 | 0.001 | 0.024 | 388.5 |
| 500 Hz | 60 s (native Linux) | 30 036 | 0 | 0 | 0.004 | 0.036 | 388.6 |
| 1000 Hz | 60 s (virtual machine) | 60 793 | 79 | 6 | 0.004 | 0.048 | 388.7 |
| 1000 Hz | 60 s (native Linux) | 60 928 | 0 | 0 | n/r | n/r | n/r |
| 1000 Hz | 60 s x3 (native Linux, fixed capture) | 60 031 each | 0 | 0 | 0.004 | 0.048 | 388.6 |
| 1000 Hz | 10 min (native Linux, old capture) | 608 127 | 0 after the 11 initial stale frames | 0 | 0.004 | n/r | 388.7 |
| 1000 Hz | 10 min (native Linux, fixed capture) | 608 511 | 0 | 0 | 0.004 | 0.048 | 388.7 |

Static IMU, 10 min, board flat and still: gyro bias [x y z] deg/s = ..., accelerometer norm error = ... mg,
gyro Allan deviation angle random walk = ... deg/√h.
