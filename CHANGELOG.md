# Changelog

## [Unreleased]

## [0.1.0]
- Timer-driven (TIM2) IMU sampling, 1 kHz default, MPU6050 over I2C1 at 400 kHz.
- Interrupt-driven I2C state machine with DMA burst read of the 14 sensor bytes.
- Lock-free SPSC ring buffer between the DMA interrupt and the main loop.
- Binary framing with CRC-16 streamed over UART with DMA; DWT cycle-counter timestamps.
- Host tools in Python and MATLAB: capture, parsing, loss/jitter/latency/IMU statistics, Allan deviation.
- Host unit tests (GoogleTest, pytest) and CI.
