// Compile-time configuration of the acquisition firmware.
//
// Everything that can be tuned lives here and can be overridden from the
// command line, e.g.  cmake --preset firmware -DSAMPLE_RATE_HZ=200
// Derived quantities are checked with static_assert so that an impossible
// combination (for example 1 kHz sampling over a 100 kHz I2C bus) fails at
// compile time instead of silently losing samples on the target.
#pragma once

#include <cstdint>

#ifndef SAMPLE_RATE_HZ
#define SAMPLE_RATE_HZ 1000  // IMU sampling rate [Hz]
#endif
#ifndef I2C_CLOCK_HZ
#define I2C_CLOCK_HZ 400000  // I2C SCL frequency [Hz]; 400 kHz is needed for 1 kHz sampling
#endif
#ifndef UART_BAUD
#define UART_BAUD 460800  // ST-LINK virtual COM port baud rate
#endif
#ifndef USE_HSE_BYPASS
#define USE_HSE_BYPASS 1  // 1 = use the 8 MHz ST-LINK MCO clock as PLL source (falls back to HSI); 0 = HSI only
#endif
#ifndef MPU_ACCEL_FS_SEL
#define MPU_ACCEL_FS_SEL 0  // 0:+-2g 1:+-4g 2:+-8g 3:+-16g
#endif
#ifndef MPU_GYRO_FS_SEL
#define MPU_GYRO_FS_SEL 0  // 0:+-250 1:+-500 2:+-1000 3:+-2000 deg/s
#endif
#ifndef MPU_DLPF_CFG
#define MPU_DLPF_CFG 1  // digital low-pass: 1 = 184 Hz accel / 188 Hz gyro (1 kHz internal rate)
#endif
#ifndef FW_VERSION
#define FW_VERSION "dev"
#endif

namespace cfg {

// ---- Clocks (see sysclk.cpp) -------------------------------------------------
inline constexpr std::uint32_t kSysClkHz = 84'000'000;   // SYSCLK = HCLK
inline constexpr std::uint32_t kApb1Hz = kSysClkHz / 2;  // APB1 prescaler /2
// With an APB1 prescaler != 1 the timer clock is 2 x PCLK1 = HCLK.
inline constexpr std::uint32_t kTimerClkHz = kApb1Hz * 2;
inline constexpr std::uint32_t kCyclesPerUs = kSysClkHz / 1'000'000;

// ---- Sampling ---------------------------------------------------------------
inline constexpr std::uint32_t kSampleRateHz = SAMPLE_RATE_HZ;
// TIM2 runs at the core clock (PSC = 0), so one tick is an integer number of
// DWT cycles and the timestamps in the log can be compared with it exactly.
inline constexpr std::uint32_t kCyclesPerTick = kTimerClkHz / kSampleRateHz;
static_assert(kSampleRateHz >= 1 && kSampleRateHz <= 1000, "sample rate must be 1..1000 Hz");
static_assert(kTimerClkHz % kSampleRateHz == 0,
              "sample rate must divide 84 MHz exactly (e.g. 1000, 500, 250, 200, 100, 50 Hz)");

// ---- I2C / MPU6050 ----------------------------------------------------------
inline constexpr std::uint8_t kMpuAddress = 0x68;  // AD0 = GND
inline constexpr std::uint32_t kI2cClockHz = I2C_CLOCK_HZ;
inline constexpr std::uint32_t kMpuBurstBytes = 14;  // ACCEL(6) + TEMP(2) + GYRO(6)
// START + addr(W) + reg + RESTART + addr(R) + 14 data bytes, 9 clocks per byte.
inline constexpr std::uint32_t kI2cBitsPerTransaction = 1 + 9 + 9 + 1 + 9 + 9 * kMpuBurstBytes;
inline constexpr std::uint32_t kI2cTransactionUs =
    (kI2cBitsPerTransaction * 1'000'000ULL + kI2cClockHz - 1) / kI2cClockHz;
static_assert(kI2cTransactionUs * 100ULL < (1'000'000ULL / kSampleRateHz) * 80ULL,
              "I2C transaction would use more than 80% of the sampling period: "
              "raise I2C_CLOCK_HZ or lower SAMPLE_RATE_HZ");

// ---- UART -------------------------------------------------------------------
inline constexpr std::uint32_t kUartBaud = UART_BAUD;
inline constexpr std::uint32_t kFrameBytes = 32;  // keep in sync with protocol.hpp
static_assert(kFrameBytes * kSampleRateHz * 10ULL * 100ULL <= kUartBaud * 80ULL,
              "UART link would be loaded above 80%: raise UART_BAUD or lower SAMPLE_RATE_HZ");

// ---- Buffers ----------------------------------------------------------------
inline constexpr std::uint32_t kRingSamples = 64;    // SPSC ring between ISR and main loop
inline constexpr std::uint32_t kTxBurstFrames = 16;  // frames per UART DMA transfer
inline constexpr std::uint32_t kWatchdogUs = 3000;   // abort an I2C transaction after 3 ms

}  // namespace cfgS