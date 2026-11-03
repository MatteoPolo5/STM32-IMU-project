// Acquisition engine.
//
//   TIM2 update IRQ (prio 0)  --- every 1/rate s -->  starts an I2C transaction
//   I2C1_EV IRQ     (prio 1)  --- state machine   -->  START, addr+W, reg, RESTART, addr+R
//   DMA1 Str0 IRQ   (prio 1)  --- 14 bytes in RAM -->  STOP, push sample to the ring
//   main loop (poll)          --- drains ring     -->  packs frames, UART DMA (DMA1 Str6)
//
// The CPU only works at the edges of a transfer (a few microseconds per event);
// the 14 data bytes are moved by DMA. TIM2 has the highest priority so the
// timestamp it captures has the smallest possible jitter. The I2C and DMA
// interrupts share one priority level, so they never preempt each other and the
// shared state below needs no locking.

#include "daq.hpp"

#include <atomic>

#include "config.hpp"
#include "hw.hpp"
#include "i2c.hpp"
#include "mpu6050.hpp"
#include "protocol.hpp"
#include "ring_buffer.hpp"
#include "stm32f4xx.h"
#include "uart.hpp"

namespace daq {

Stats g_stats{};

namespace {

enum class State : std::uint8_t {
  Idle,
  WaitStartW,  // START issued, waiting for SB
  WaitAddrW,   // address+W sent, waiting for ADDR
  WaitBtf,     // register pointer sent, waiting for BTF
  WaitStartR,  // repeated START issued, waiting for SB
  WaitAddrR,   // address+R sent, waiting for ADDR
  Receiving,   // DMA is moving the 14 data bytes
};

constexpr std::uint32_t kLisrFlags0 =
    DMA_LIFCR_CTCIF0 | DMA_LIFCR_CHTIF0 | DMA_LIFCR_CTEIF0 | DMA_LIFCR_CDMEIF0 | DMA_LIFCR_CFEIF0;

volatile State g_state = State::Idle;
std::uint32_t g_next_seq = 0;      // only touched by the TIM2 ISR
std::uint32_t g_start_cycles = 0;  // transaction start, for the watchdog
std::atomic<std::uint32_t> g_dropped{0};

protocol::Sample g_cur;  // sample being acquired; g_cur.raw is the DMA target
SpscRing<protocol::Sample, cfg::kRingSamples> g_ring;

alignas(4) std::uint8_t g_txbuf[cfg::kTxBurstFrames * protocol::kFrameSize];
std::uint32_t g_led_next = cfg::kSampleRateHz;

inline void count_drop() {
  g_dropped.fetch_add(1, std::memory_order_relaxed);
}

void dma_rx_arm() {
  DMA1->LIFCR = kLisrFlags0;
  DMA1_Stream0->M0AR = reinterpret_cast<std::uint32_t>(g_cur.raw.data());
  DMA1_Stream0->NDTR = protocol::kPayloadSize;
  DMA1_Stream0->CR |= DMA_SxCR_EN;
}

void dma_rx_disable() {
  DMA1_Stream0->CR &= ~DMA_SxCR_EN;
  hw::wait_until([] { return !(DMA1_Stream0->CR & DMA_SxCR_EN); }, 100);
  DMA1->LIFCR = kLisrFlags0;
}

// Drops the transaction in flight and brings the I2C peripheral back to a known state.
void abort_transaction() {
  dma_rx_disable();
  i2c::reset_peripheral();  // SWRST also releases SCL/SDA and clears all error flags
  g_state = State::Idle;
}

void on_tick(std::uint32_t now) {
  ++g_stats.ticks;
  const std::uint32_t seq = g_next_seq++;  // advances even when the sample is dropped
  if (g_state != State::Idle) {
    ++g_stats.overruns;
    count_drop();
    return;
  }
  g_cur.seq = seq;
  g_cur.t_tick = now;
  g_start_cycles = now;
  g_state = State::WaitStartW;
  I2C1->CR2 |= I2C_CR2_ITEVTEN | I2C_CR2_ITERREN;
  I2C1->CR1 |= I2C_CR1_ACK | I2C_CR1_START;
}

void check_watchdog() {
  if (g_state == State::Idle) return;
  if (hw::cycles() - g_start_cycles < cfg::kWatchdogUs * cfg::kCyclesPerUs) return;
  __disable_irq();
  if (g_state != State::Idle) {  // re-check: the ISR may have finished meanwhile
    abort_transaction();
    ++g_stats.watchdog_aborts;
    count_drop();
  }
  __enable_irq();
}

void drain_to_uart() {
  if (uart::tx_busy()) return;
  protocol::Sample s;
  std::size_t n = 0;
  while (n < cfg::kTxBurstFrames && g_ring.pop(s)) {
    protocol::pack_frame(s, g_txbuf + n * protocol::kFrameSize);
    ++n;
  }
  if (n == 0) return;
  uart::start_tx(g_txbuf, n * protocol::kFrameSize);
  g_stats.frames_sent += static_cast<std::uint32_t>(n);
}

void heartbeat() {
  // LD2 (PA5) toggles once per second of streamed data.
  if (g_stats.frames_sent >= g_led_next) {
    g_led_next += cfg::kSampleRateHz;
    GPIOA->ODR ^= (1U << 5);
  }
}

}  // namespace

void init() {
  RCC->AHB1ENR |= RCC_AHB1ENR_DMA1EN;
  RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
  (void)RCC->APB1ENR;

  // DMA1 Stream0, channel 1 = I2C1_RX. Peripheral -> memory, 8-bit, memory increment.
  dma_rx_disable();
  DMA1_Stream0->PAR = reinterpret_cast<std::uint32_t>(&I2C1->DR);
  DMA1_Stream0->FCR = 0;
  DMA1_Stream0->CR =
      (1U << DMA_SxCR_CHSEL_Pos) | DMA_SxCR_MINC | DMA_SxCR_PL_1 /* high */ | DMA_SxCR_TCIE | DMA_SxCR_TEIE;

  // TIM2 (32-bit) counts at the core clock; one update event per sample period.
  TIM2->PSC = 0;
  TIM2->ARR = cfg::kCyclesPerTick - 1;
  TIM2->EGR = TIM_EGR_UG;  // load the registers...
  TIM2->SR = 0;            // ...and discard the update flag that this raised
  TIM2->DIER = TIM_DIER_UIE;

  NVIC_SetPriority(TIM2_IRQn, 0);
  NVIC_SetPriority(I2C1_EV_IRQn, 1);
  NVIC_SetPriority(I2C1_ER_IRQn, 1);
  NVIC_SetPriority(DMA1_Stream0_IRQn, 1);
  NVIC_EnableIRQ(TIM2_IRQn);
  NVIC_EnableIRQ(I2C1_EV_IRQn);
  NVIC_EnableIRQ(I2C1_ER_IRQn);
  NVIC_EnableIRQ(DMA1_Stream0_IRQn);
}

void start() {
  TIM2->CNT = 0;
  TIM2->CR1 |= TIM_CR1_CEN;
}

void poll() {
  check_watchdog();
  drain_to_uart();
  heartbeat();
}

// ---- Interrupt service routine bodies (the extern "C" entry points are at the end of the file) ----
static void isr_tim2() {
  const std::uint32_t now = hw::cycles();  // first thing: timestamp
  TIM2->SR = ~static_cast<std::uint32_t>(TIM_SR_UIF);
  on_tick(now);
}

static void isr_i2c_ev() {
  const std::uint32_t sr1 = I2C1->SR1;
  switch (g_state) {
    case State::WaitStartW:
      if (sr1 & I2C_SR1_SB) {
        I2C1->DR = static_cast<std::uint32_t>(cfg::kMpuAddress << 1);
        g_state = State::WaitAddrW;
      }
      break;
    case State::WaitAddrW:
      if (sr1 & I2C_SR1_ADDR) {
        (void)I2C1->SR2;  // clear ADDR
        I2C1->DR = mpu6050::kRegAccelXoutH;
        g_state = State::WaitBtf;
      }
      break;
    case State::WaitBtf:
      if (sr1 & I2C_SR1_BTF) {
        I2C1->CR1 |= I2C_CR1_START;  // repeated START
        g_state = State::WaitStartR;
      }
      break;
    case State::WaitStartR:
      if (sr1 & I2C_SR1_SB) {
        I2C1->DR = static_cast<std::uint32_t>((cfg::kMpuAddress << 1) | 1U);
        g_state = State::WaitAddrR;
      }
      break;
    case State::WaitAddrR:
      if (sr1 & I2C_SR1_ADDR) {
        dma_rx_arm();  // the stream must be enabled before ADDR is cleared
        // LAST: NACK the final byte. Event interrupts are switched off while DMA
        // runs, otherwise a pending BTF would retrigger this ISR in a loop.
        I2C1->CR2 = (I2C1->CR2 | I2C_CR2_DMAEN | I2C_CR2_LAST) & ~I2C_CR2_ITEVTEN;
        (void)I2C1->SR2;  // clear ADDR -> reception starts
        g_state = State::Receiving;
      }
      break;
    default:
      I2C1->CR2 &= ~I2C_CR2_ITEVTEN;  // spurious event: mask it
      break;
  }
}

static void isr_i2c_er() {
  const std::uint32_t sr1 = I2C1->SR1;
  if (sr1 & (I2C_SR1_BERR | I2C_SR1_ARLO | I2C_SR1_AF | I2C_SR1_OVR | I2C_SR1_TIMEOUT)) {
    ++g_stats.i2c_errors;
    if (g_state != State::Idle) count_drop();
    abort_transaction();
  }
}

static void isr_dma_i2c_rx() {
  const std::uint32_t now = hw::cycles();
  const std::uint32_t lisr = DMA1->LISR;
  DMA1->LIFCR = kLisrFlags0;
  std::atomic_signal_fence(std::memory_order_seq_cst);  // DMA wrote g_cur.raw behind the compiler's back

  if (lisr & DMA_LISR_TEIF0) {
    ++g_stats.i2c_errors;
    count_drop();
    abort_transaction();
    return;
  }
  if ((lisr & DMA_LISR_TCIF0) && g_state == State::Receiving) {
    I2C1->CR2 &= ~(I2C_CR2_DMAEN | I2C_CR2_LAST);
    I2C1->CR1 |= I2C_CR1_STOP;

    g_cur.t_done = now;
    g_cur.dropped = static_cast<std::uint16_t>(g_dropped.load(std::memory_order_relaxed));
    const std::uint32_t latency = now - g_cur.t_tick;
    if (latency > g_stats.max_latency_cycles) g_stats.max_latency_cycles = latency;

    if (g_ring.push(g_cur)) {
      ++g_stats.completed;
    } else {
      ++g_stats.ring_overflows;
      count_drop();
    }
    g_state = State::Idle;
  }
}

}  // namespace daq

extern "C" {
void TIM2_IRQHandler() {
  daq::isr_tim2();
}
void I2C1_EV_IRQHandler() {
  daq::isr_i2c_ev();
}
void I2C1_ER_IRQHandler() {
  daq::isr_i2c_er();
}
void DMA1_Stream0_IRQHandler() {
  daq::isr_dma_i2c_rx();
}
}
