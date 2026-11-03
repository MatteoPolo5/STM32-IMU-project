#include "mpu6050.hpp"

#include "config.hpp"
#include "hw.hpp"
#include "i2c.hpp"

namespace mpu6050 {

bool init(std::uint8_t& who_am_i) {
  constexpr std::uint8_t dev = cfg::kMpuAddress;

  if (!i2c::read_reg(dev, kRegWhoAmI, who_am_i)) return false;

  // Device reset, then wait for the reset bit to self-clear.
  if (!i2c::write_reg(dev, kRegPwrMgmt1, 0x80)) return false;
  hw::delay_ms(100);
  std::uint8_t pwr = 0x80;
  for (int i = 0; i < 50 && (pwr & 0x80); ++i) {
    if (!i2c::read_reg(dev, kRegPwrMgmt1, pwr)) return false;
    hw::delay_ms(2);
  }

  // Wake up, clock source = PLL with X-gyro reference (more stable than the internal RC).
  if (!i2c::write_reg(dev, kRegPwrMgmt1, 0x01)) return false;
  hw::delay_ms(50);

  // Gyro output rate is 1 kHz when the DLPF is enabled; divider 0 -> 1 kHz internal rate.
  if (!i2c::write_reg(dev, kRegSmplrtDiv, 0)) return false;
  if (!i2c::write_reg(dev, kRegConfig, static_cast<std::uint8_t>(MPU_DLPF_CFG))) return false;
  if (!i2c::write_reg(dev, kRegGyroConfig, static_cast<std::uint8_t>(MPU_GYRO_FS_SEL << 3))) return false;
  if (!i2c::write_reg(dev, kRegAccelConfig, static_cast<std::uint8_t>(MPU_ACCEL_FS_SEL << 3))) return false;
  return true;
}

}  // namespace mpu6050
