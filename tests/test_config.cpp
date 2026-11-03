#include <gtest/gtest.h>

#include "config.hpp"
#include "protocol.hpp"

// The static_asserts in config.hpp already stop impossible builds; these tests
// document the numbers for the default configuration (1 kHz, 400 kHz I2C, 460800 baud).
TEST(Config, FrameSizeMatchesProtocol) {
  EXPECT_EQ(cfg::kFrameBytes, protocol::kFrameSize);
}

TEST(Config, TickIsAnIntegerNumberOfCycles) {
  EXPECT_EQ(cfg::kCyclesPerTick * cfg::kSampleRateHz, cfg::kTimerClkHz);
}

#if SAMPLE_RATE_HZ == 1000 && I2C_CLOCK_HZ == 400000 && UART_BAUD == 460800
TEST(Config, DefaultBudgets) {
  EXPECT_EQ(cfg::kCyclesPerTick, 84000u);
  EXPECT_LT(cfg::kI2cTransactionUs, 400u);                                 // ~388 us of a 1000 us period
  EXPECT_LT(cfg::kFrameBytes * cfg::kSampleRateHz * 10u, cfg::kUartBaud);  // < 100 % link load
}
#endif
