#include "i2c.hpp"

#include "config.hpp"
#include "hw.hpp"
#include "stm32f4xx.h"

namespace i2c {

namespace {

constexpr unsigned kSclPin = 8;  // PB8
constexpr unsigned kSdaPin = 9;  // PB9
constexpr std::uint32_t kTimeoutUs = 2000;

// Slave may hold SDA low after a reset in the middle of a transfer. Clock SCL
// up to 9 times, then generate a STOP, as described in the I2C spec.
void recover_bus() {
  GPIOB->BSRR = (1U << kSclPin) | (1U << kSdaPin);  // release both lines
  hw::gpio_out(GPIOB, kSclPin, /*open_drain=*/true, hw::Pull::Up);
  hw::gpio_out(GPIOB, kSdaPin, /*open_drain=*/true, hw::Pull::Up);
  hw::delay_us(10);
  for (int i = 0; i < 9 && !(GPIOB->IDR & (1U << kSdaPin)); ++i) {
    GPIOB->BSRR = (1U << (kSclPin + 16));
    hw::delay_us(5);
    GPIOB->BSRR = (1U << kSclPin);
    hw::delay_us(5);
  }
  GPIOB->BSRR = (1U << (kSdaPin + 16));  // STOP: SDA low -> SCL high -> SDA high
  hw::delay_us(5);
  GPIOB->BSRR = (1U << kSclPin);
  hw::delay_us(5);
  GPIOB->BSRR = (1U << kSdaPin);
  hw::delay_us(5);
}

void clear_errors() {
  I2C1->SR1 &= ~(I2C_SR1_BERR | I2C_SR1_ARLO | I2C_SR1_AF | I2C_SR1_OVR | I2C_SR1_TIMEOUT);
}

bool wait_sr1(std::uint32_t mask) {
  return hw::wait_until(
             [mask] {
               const std::uint32_t sr1 = I2C1->SR1;
               return (sr1 & mask) != 0 || (sr1 & (I2C_SR1_AF | I2C_SR1_BERR | I2C_SR1_ARLO)) != 0;
             },
             kTimeoutUs) &&
         (I2C1->SR1 & (I2C_SR1_AF | I2C_SR1_BERR | I2C_SR1_ARLO)) == 0;
}

bool wait_idle() {
  return hw::wait_until([] { return !(I2C1->SR2 & I2C_SR2_BUSY); }, kTimeoutUs);
}

void abort_transfer() {
  I2C1->CR1 |= I2C_CR1_STOP;
  clear_errors();
}

}  // namespace

void reset_peripheral() {
  I2C1->CR1 = I2C_CR1_SWRST;
  I2C1->CR1 = 0;

  constexpr std::uint32_t kPclkMhz = cfg::kApb1Hz / 1'000'000;  // 42
  I2C1->CR2 = kPclkMhz;                                         // FREQ field
  if (cfg::kI2cClockHz <= 100'000) {
    // Standard mode: Thigh = Tlow = CCR * Tpclk
    I2C1->CCR = cfg::kApb1Hz / (2 * cfg::kI2cClockHz);
    I2C1->TRISE = kPclkMhz + 1;  // 1000 ns max rise time
  } else {
    // Fast mode, DUTY = 0: Tlow = 2 * CCR * Tpclk, Thigh = CCR * Tpclk
    I2C1->CCR = I2C_CCR_FS | (cfg::kApb1Hz / (3 * cfg::kI2cClockHz));  // 42 MHz / 1.2 MHz = 35
    I2C1->TRISE = (kPclkMhz * 300) / 1000 + 1;                         // 300 ns max rise time
  }
  I2C1->CR1 = I2C_CR1_PE | I2C_CR1_ACK;
}

void init() {
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOBEN;
  RCC->APB1ENR |= RCC_APB1ENR_I2C1EN;
  (void)RCC->APB1ENR;

  recover_bus();
  hw::gpio_af(GPIOB, kSclPin, 4, /*open_drain=*/true, hw::Pull::Up);  // I2C1_SCL = AF4
  hw::gpio_af(GPIOB, kSdaPin, 4, /*open_drain=*/true, hw::Pull::Up);  // I2C1_SDA = AF4
  reset_peripheral();
}

bool write_reg(std::uint8_t dev, std::uint8_t reg, std::uint8_t value) {
  bool ok = false;
  I2C1->CR1 |= I2C_CR1_START;
  do {
    if (!wait_sr1(I2C_SR1_SB)) break;
    I2C1->DR = static_cast<std::uint32_t>(dev << 1);
    if (!wait_sr1(I2C_SR1_ADDR)) break;
    (void)I2C1->SR2;  // clears ADDR (SR1 read happened in wait_sr1)
    if (!wait_sr1(I2C_SR1_TXE)) break;
    I2C1->DR = reg;
    if (!wait_sr1(I2C_SR1_TXE)) break;
    I2C1->DR = value;
    if (!wait_sr1(I2C_SR1_BTF)) break;
    ok = true;
  } while (false);
  abort_transfer();  // STOP (also the normal end of a write)
  if (!wait_idle()) ok = false;
  return ok;
}

bool read_reg(std::uint8_t dev, std::uint8_t reg, std::uint8_t& value) {
  bool ok = false;
  I2C1->CR1 |= I2C_CR1_START | I2C_CR1_ACK;
  do {
    if (!wait_sr1(I2C_SR1_SB)) break;
    I2C1->DR = static_cast<std::uint32_t>(dev << 1);
    if (!wait_sr1(I2C_SR1_ADDR)) break;
    (void)I2C1->SR2;
    if (!wait_sr1(I2C_SR1_TXE)) break;
    I2C1->DR = reg;
    if (!wait_sr1(I2C_SR1_BTF)) break;

    I2C1->CR1 |= I2C_CR1_START;  // repeated start
    if (!wait_sr1(I2C_SR1_SB)) break;
    I2C1->DR = static_cast<std::uint32_t>((dev << 1) | 1U);
    if (!wait_sr1(I2C_SR1_ADDR)) break;
    // Single-byte reception (RM0390): NACK it, clear ADDR, then program STOP.
    I2C1->CR1 &= ~I2C_CR1_ACK;
    (void)I2C1->SR2;
    I2C1->CR1 |= I2C_CR1_STOP;
    if (!wait_sr1(I2C_SR1_RXNE)) break;
    value = static_cast<std::uint8_t>(I2C1->DR);
    ok = true;
  } while (false);
  if (!ok) abort_transfer();
  if (!wait_idle()) ok = false;
  I2C1->CR1 |= I2C_CR1_ACK;
  return ok;
}

}  // namespace i2c
