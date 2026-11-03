# Validation plan and results

The goal of this project is not "it prints IMU data" but "it samples at a known rate, and I can prove it".
Every test has a pass criterion and the command that produces the number.

## Tests

| ID | What | How | Pass criterion |
|---|---|---|---|
| T1 | Sensor bring-up | banner shows `who_am_i=0x68` | present |
| T2 | No lost samples | 10 min capture at 1 kHz, `analyze` | `frames_lost == 0`, `crc_errors == 0` |
| T3 | Sampling rate | `rate_hz_measured` from the log | within 1 ppm of 1000 Hz (same clock domain) |
| T4 | ISR-entry jitter (from log) | `jitter_us` in `summary.json` | report rms, peak-to-peak, max (no fixed limit, it is a measurement) |
| T5 | Jitter, independent check | logic analyzer on a pin toggled in the TIM2 ISR | compare with T4 |
| T6 | Acquisition latency | `latency_us` | max < 80 % of the period |
| T7 | Static IMU sanity | board still on the table | `abs(norm(a) - 1 g) < 30 mg`, gyro bias small and stable |
| T8 | Fault injection: stalled main loop | debug build with `hw::delay_ms(200)` added to `daq::poll()` | `ring_overflows` increases, gaps are visible in `seq`, stream recovers when the stall is removed |
| T9 | Fault injection: I2C | disconnect SDA for 1 s during streaming, reconnect | `i2c_errors` / `watchdog_aborts` increase, streaming resumes by itself |
| T10 | Rate sweep | build with 200 / 500 / 1000 Hz | table below |

## How to reproduce

```bash
cd tools
python -m imu_daq capture --port /dev/ttyACM0 --duration 600 --out ../data/run_1khz.bin
python -m imu_daq analyze ../data/run_1khz.bin --rate 1000 --out ../results/run_1khz
# MATLAB / Octave
#   r = analyze_log('data/run_1khz.bin', 1000);
```

`analyze` writes `summary.json` and plots (`timing_jitter.png`, `latency.png`, `imu_signals.png`, `allan_gyro.png`).

## Results (to be filled in with measured data)

> The numbers below are intentionally empty: fill them in from *your* captures, together with the date,
> board revision, firmware commit (`git describe`), toolchain version and cable/wiring notes.
> Copy the plots into `docs/images/` and link them from the README.

| Rate | Duration | Frames | Lost | CRC errors | Jitter rms [µs] | Jitter p-p [µs] | Latency max [µs] |
|---|---|---|---|---|---|---|---|
| 200 Hz | | | | | | | |
| 500 Hz | | | | | | | |
| 1000 Hz | | | | | | | |

Static IMU (10 min, board still): gyro bias [x y z] deg/s = ..., accelerometer norm error = ... mg,
gyro Allan deviation angle random walk = ... deg/√h.
