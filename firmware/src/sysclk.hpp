#pragma once

namespace sysclk {

enum class Source { Hsi, HseBypass };

// SYSCLK = HCLK = 84 MHz, APB1 = 42 MHz (timers 84 MHz), APB2 = 84 MHz.
// Uses the 8 MHz ST-LINK MCO if USE_HSE_BYPASS=1 and it starts, HSI otherwise.
Source init();

}  // namespace sysclk
