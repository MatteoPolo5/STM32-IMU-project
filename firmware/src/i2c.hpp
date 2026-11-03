#pragma once

#include <cstdint>

namespace i2c {

// I2C1 on PB8 (SCL / D15) and PB9 (SDA / D14), open-drain, internal pull-ups
// enabled as a backup for the module's own pull-up resistors.
void init();

// Re-initialises the peripheral (SWRST + timing). Safe to call from an ISR.
void reset_peripheral();

// Blocking single-register accessors, used only during sensor bring-up.
bool write_reg(std::uint8_t dev, std::uint8_t reg, std::uint8_t value);
bool read_reg(std::uint8_t dev, std::uint8_t reg, std::uint8_t& value);

}  // namespace i2c
