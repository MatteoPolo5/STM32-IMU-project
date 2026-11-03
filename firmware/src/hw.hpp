// Tiny register-level helpers shared by the drivers: DWT cycle counter,
// busy-wait with timeout, GPIO alternate-function setup.
#pragma once

#include <cstdint>

#include "config.hpp"
#include "stm32f4xx.h"

namespace hw {

// Enables the DWT cycle counter (32-bit, counts core clock cycles).
inline void dwt_init() {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

inline std::uint32_t cycles() {
  return DWT->CYCCNT;
}

inline void delay_us(std::uint32_t us) {
  const std::uint32_t start = cycles();
  const std::uint32_t ticks = us * cfg::kCyclesPerUs;
  while (cycles() - start < ticks) {
  }
}
inline void delay_ms(std::uint32_t ms) {
  while (ms--) delay_us(1000);
}

// Polls `cond()` until it returns true or `timeout_us` elapsed.
template <typename F>
inline bool wait_until(F cond, std::uint32_t timeout_us) {
  const std::uint32_t start = cycles();
  const std::uint32_t ticks = timeout_us * cfg::kCyclesPerUs;
  while (!cond()) {
    if (cycles() - start > ticks) return false;
  }
  return true;
}

enum class Pull : std::uint32_t { None = 0, Up = 1, Down = 2 };

// Configures a pin as alternate function (very-high speed).
inline void gpio_af(GPIO_TypeDef* port, unsigned pin, unsigned af, bool open_drain, Pull pull) {
  port->MODER = (port->MODER & ~(3U << (pin * 2))) | (2U << (pin * 2));
  port->OTYPER = open_drain ? (port->OTYPER | (1U << pin)) : (port->OTYPER & ~(1U << pin));
  port->OSPEEDR |= (3U << (pin * 2));
  port->PUPDR = (port->PUPDR & ~(3U << (pin * 2))) | (static_cast<std::uint32_t>(pull) << (pin * 2));
  const unsigned reg = pin >> 3;
  const unsigned shift = (pin & 7U) * 4U;
  port->AFR[reg] = (port->AFR[reg] & ~(0xFU << shift)) | (af << shift);
}

// Configures a pin as general-purpose output.
inline void gpio_out(GPIO_TypeDef* port, unsigned pin, bool open_drain, Pull pull) {
  port->MODER = (port->MODER & ~(3U << (pin * 2))) | (1U << (pin * 2));
  port->OTYPER = open_drain ? (port->OTYPER | (1U << pin)) : (port->OTYPER & ~(1U << pin));
  port->PUPDR = (port->PUPDR & ~(3U << (pin * 2))) | (static_cast<std::uint32_t>(pull) << (pin * 2));
}

}  // namespace hw
