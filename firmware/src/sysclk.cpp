#include "sysclk.hpp"

#include <cstdint>

#include "config.hpp"
#include "stm32f4xx.h"

namespace sysclk {

namespace {
// Crude timeout (DWT is not running yet): ~tens of ms at the 16 MHz HSI.
constexpr std::uint32_t kSpinLimit = 400000;

template <typename F>
bool spin_until(F cond) {
  for (std::uint32_t i = 0; i < kSpinLimit; ++i) {
    if (cond()) return true;
  }
  return false;
}
}  // namespace

Source init() {
  // 84 MHz at 2.7-3.6 V needs 2 wait states. Prefetch + instruction/data
  // caches keep the effective CPU speed (and ISR latency) predictable.
  FLASH->ACR = FLASH_ACR_LATENCY_2WS | FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN;

  bool use_hse = false;
#if USE_HSE_BYPASS
  RCC->CR |= RCC_CR_HSEBYP | RCC_CR_HSEON;
  use_hse = spin_until([] { return (RCC->CR & RCC_CR_HSERDY) != 0; });
  if (!use_hse) {
    RCC->CR &= ~RCC_CR_HSEON;
    RCC->CR &= ~RCC_CR_HSEBYP;
  }
#endif

  // PLL input must be 2 MHz: HSI 16 MHz / 8, or HSE 8 MHz / 4.
  // VCO = 2 MHz * 168 = 336 MHz;  SYSCLK = VCO / 4 = 84 MHz.
  const std::uint32_t pllm = use_hse ? 4U : 8U;
  RCC->PLLCFGR = (pllm << RCC_PLLCFGR_PLLM_Pos) | (168U << RCC_PLLCFGR_PLLN_Pos) |
                 (1U << RCC_PLLCFGR_PLLP_Pos) /* /4 */ | (7U << RCC_PLLCFGR_PLLQ_Pos) |
                 (2U << RCC_PLLCFGR_PLLR_Pos) | (use_hse ? RCC_PLLCFGR_PLLSRC_HSE : 0U);

  // Bus prescalers before switching: AHB /1, APB1 /2 (42 MHz), APB2 /1.
  RCC->CFGR = (RCC->CFGR & ~(RCC_CFGR_HPRE | RCC_CFGR_PPRE1 | RCC_CFGR_PPRE2)) | RCC_CFGR_PPRE1_DIV2;

  RCC->CR |= RCC_CR_PLLON;
  spin_until([] { return (RCC->CR & RCC_CR_PLLRDY) != 0; });

  RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
  spin_until([] { return (RCC->CFGR & RCC_CFGR_SWS) == RCC_CFGR_SWS_PLL; });

  return use_hse ? Source::HseBypass : Source::Hsi;
}

}  // namespace sysclk
