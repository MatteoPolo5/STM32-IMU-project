#include "uart.hpp"

#include <atomic>

#include "config.hpp"
#include "hw.hpp"
#include "stm32f4xx.h"

namespace uart {

namespace {
std::atomic<bool> g_busy{false};
volatile std::uint32_t g_errors = 0;

constexpr std::uint32_t kStream6Flags =
    DMA_HIFCR_CTCIF6 | DMA_HIFCR_CHTIF6 | DMA_HIFCR_CTEIF6 | DMA_HIFCR_CDMEIF6 | DMA_HIFCR_CFEIF6;
}  // namespace

void init() {
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_DMA1EN;
  RCC->APB1ENR |= RCC_APB1ENR_USART2EN;
  (void)RCC->APB1ENR;  // read-back: let the clock gate settle

  hw::gpio_af(GPIOA, 2, 7, /*open_drain=*/false, hw::Pull::None);  // USART2_TX = AF7

  // 16x oversampling: BRR = fPCLK1 / baud (rounded). 42 MHz / 460800 -> 91 (0.16 % error).
  USART2->BRR = (cfg::kApb1Hz + cfg::kUartBaud / 2) / cfg::kUartBaud;
  USART2->CR3 = USART_CR3_DMAT;
  USART2->CR1 = USART_CR1_UE | USART_CR1_TE;

  // DMA1 Stream6, channel 4 = USART2_TX. Memory -> peripheral, memory increment.
  DMA1_Stream6->CR &= ~DMA_SxCR_EN;
  while (DMA1_Stream6->CR & DMA_SxCR_EN) {
  }
  DMA1->HIFCR = kStream6Flags;
  DMA1_Stream6->PAR = reinterpret_cast<std::uint32_t>(&USART2->DR);
  DMA1_Stream6->FCR = 0;  // direct mode
  DMA1_Stream6->CR = (4U << DMA_SxCR_CHSEL_Pos) | DMA_SxCR_DIR_0 | DMA_SxCR_MINC |
                     DMA_SxCR_PL_0 /* medium priority */ | DMA_SxCR_TCIE | DMA_SxCR_TEIE;

  NVIC_SetPriority(DMA1_Stream6_IRQn, 3);
  NVIC_EnableIRQ(DMA1_Stream6_IRQn);
}

void write(const char* s) {
  while (*s) {
    while (!(USART2->SR & USART_SR_TXE)) {
    }
    USART2->DR = static_cast<std::uint8_t>(*s++);
  }
  while (!(USART2->SR & USART_SR_TC)) {
  }
}

void write_dec(std::uint32_t v) {
  char buf[11];
  int n = 0;
  do {
    buf[n++] = static_cast<char>('0' + v % 10);
    v /= 10;
  } while (v);
  char out[12];
  for (int i = 0; i < n; ++i) out[i] = buf[n - 1 - i];
  out[n] = '\0';
  write(out);
}

void write_hex8(std::uint8_t v) {
  static const char kDigits[] = "0123456789ABCDEF";
  const char out[5] = {'0', 'x', kDigits[v >> 4], kDigits[v & 0xF], '\0'};
  write(out);
}

bool start_tx(const std::uint8_t* data, std::size_t len) {
  if (len == 0 || g_busy.load(std::memory_order_acquire)) return false;
  g_busy.store(true, std::memory_order_relaxed);
  DMA1->HIFCR = kStream6Flags;
  USART2->SR = ~static_cast<std::uint32_t>(USART_SR_TC);  // TC is rc_w0
  DMA1_Stream6->M0AR = reinterpret_cast<std::uint32_t>(data);
  DMA1_Stream6->NDTR = static_cast<std::uint32_t>(len);
  DMA1_Stream6->CR |= DMA_SxCR_EN;
  return true;
}

bool tx_busy() {
  return g_busy.load(std::memory_order_acquire);
}
std::uint32_t tx_errors() {
  return g_errors;
}

}  // namespace uart

extern "C" void DMA1_Stream6_IRQHandler() {
  const std::uint32_t hisr = DMA1->HISR;
  DMA1->HIFCR = uart::kStream6Flags;
  if (hisr & DMA_HISR_TEIF6) uart::g_errors = uart::g_errors + 1;
  // On TC (or error) the stream has disabled itself; the buffer is free again.
  uart::g_busy.store(false, std::memory_order_release);
}
