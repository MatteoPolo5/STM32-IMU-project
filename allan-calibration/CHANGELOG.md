# Changelog

## [Unreleased]
- `analyze` reports gyro angle random walk and bias instability from the Allan deviation (Python and MATLAB), with checks
  that the curve is on the -1/2 slope and that a minimum was actually observed.
- `calibrate`: six-position accelerometer offset/sensitivity and gyro bias, validated on a held-out capture
  (Python `calibration.py`, MATLAB `calibrate_six_position.m`, tests in pytest and Octave).
- `capture` writes a `.times.csv` with host timestamps next to the log and `analyze` prints the frame rate against the
  host clock.
- MATLAB gained the Allan deviation (it was listed in 0.1.0 but only the Python tool had it).

## [0.1.0]
- Timer-driven (TIM2) IMU sampling, 1 kHz default, MPU6050 over I2C1 at 400 kHz.
- Interrupt-driven I2C state machine with DMA burst read of the 14 sensor bytes.
- Lock-free SPSC ring buffer between the DMA interrupt and the main loop.
- Binary framing with CRC-16 streamed over UART with DMA; DWT cycle-counter timestamps.
- Host tools in Python and MATLAB: capture, parsing, loss/jitter/latency/IMU statistics, Allan deviation.
- Host unit tests (GoogleTest, pytest) and CI.
- Validated on hardware (see `docs/validation.md`): 0 lost frames in 10 min at 1 kHz, 60 s runs at 200 / 500 / 1000 Hz,
  I2C disconnection test (firmware resumes by itself, `dropped` counter equals the gap).
- Clock: the ST-LINK 8 MHz output (HSE bypass) is now the default PLL source, with automatic fallback to HSI
  (`-DUSE_HSE_BYPASS=OFF` for HSI only). On the test board the HSI ran about 1.3 % fast. The banner reports `clk=HSE` or `clk=HSI`.
- `capture` discards the first second after opening the port (`--warmup`): frames buffered in the ST-LINK while nobody was
  reading appeared as a false sequence jump at the start of a log.
- Build compatibility: `-DOPENOCD_INTERFACE=...` for OpenOCD older than 0.11 (Ubuntu 20.04); linker script without
  `(READONLY)` so that binutils older than 2.35 can link it.
- Known open points: sampling rate verified only to about 0.3 % (not 100 ppm); occasional "sensor not answering" after
  a flash seen twice and not reproduced in 5 repeats; static IMU bias differs between sessions.
