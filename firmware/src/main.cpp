// E3 - IMU data acquisition on the NUCLEO-F446RE.
//
// MPU6050 (I2C1) is sampled by a hardware timer, read out with DMA and streamed
// as binary frames over the ST-LINK virtual COM port. See README.md.

#include <cstdint>

#include "config.hpp"
#include "daq.hpp"
#include "hw.hpp"
#include "i2c.hpp"
#include "mpu6050.hpp"
#include "stm32f4xx.h"
#include "sysclk.hpp"
#include "uart.hpp"

namespace {

void led_init() {
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
  hw::gpio_out(GPIOA, 5, /*open_drain=*/false, hw::Pull::None);  // LD2 = PA5
}

[[noreturn]] void fatal(const char* msg) {
  for (;;) {
    uart::write("\r\nFATAL: ");
    uart::write(msg);
    uart::write("\r\n");
    for (int i = 0; i < 10; ++i) {  // fast blink for ~1 s, then repeat the message
      GPIOA->ODR ^= (1U << 5);
      hw::delay_ms(50);
    }
  }
}

}  // namespace

int main() {
  const sysclk::Source clk = sysclk::init();
  hw::dwt_init();
  led_init();
  uart::init();

  uart::write("\r\nE3-DAQ fw=" FW_VERSION " rate=");
  uart::write_dec(cfg::kSampleRateHz);
  uart::write("Hz i2c=");
  uart::write_dec(cfg::kI2cClockHz / 1000);
  uart::write("kHz baud=");
  uart::write_dec(cfg::kUartBaud);
  uart::write(clk == sysclk::Source::HseBypass ? " clk=HSE" : " clk=HSI");

  i2c::init();
  std::uint8_t who = 0;
  if (!mpu6050::init(who)) fatal("MPU6050 not responding on I2C1 (PB8=SCL, PB9=SDA, addr 0x68)");

  uart::write(" who_am_i=");
  uart::write_hex8(who);
  if (who != mpu6050::kWhoAmIExpected) uart::write(" (unexpected, clone?)");
  uart::write("\r\nSTREAM\r\n");  // binary frames follow this line

  daq::init();
  daq::start();
  for (;;) {
    daq::poll();
  }
}
