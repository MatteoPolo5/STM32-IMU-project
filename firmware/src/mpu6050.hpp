#pragma once

#include <cstdint>

namespace mpu6050 {

inline constexpr std::uint8_t kRegSmplrtDiv = 0x19;
inline constexpr std::uint8_t kRegConfig = 0x1A;
inline constexpr std::uint8_t kRegGyroConfig = 0x1B;
inline constexpr std::uint8_t kRegAccelConfig = 0x1C;
inline constexpr std::uint8_t kRegAccelXoutH = 0x3B;  // start of the 14-byte burst
inline constexpr std::uint8_t kRegPwrMgmt1 = 0x6B;
inline constexpr std::uint8_t kRegWhoAmI = 0x75;
inline constexpr std::uint8_t kWhoAmIExpected = 0x68;

// Resets and configures the sensor (blocking). Returns false on an I2C error.
// `who_am_i` receives the identity register so the caller can report it.
bool init(std::uint8_t& who_am_i);

}  // namespace mpu6050
