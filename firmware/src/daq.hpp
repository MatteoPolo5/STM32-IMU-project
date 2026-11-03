#pragma once

#include <cstdint>

namespace daq {

// Counters readable from GDB (`print daq::g_stats`) or a watch window.
struct Stats {
  volatile std::uint32_t ticks;               // timer interrupts seen
  volatile std::uint32_t completed;           // samples stored in the ring
  volatile std::uint32_t overruns;            // tick arrived while a transaction was still running
  volatile std::uint32_t ring_overflows;      // ring full when a sample completed
  volatile std::uint32_t i2c_errors;          // BERR / ARLO / AF / DMA error
  volatile std::uint32_t watchdog_aborts;     // transaction exceeded cfg::kWatchdogUs
  volatile std::uint32_t frames_sent;         // frames handed to the UART DMA
  volatile std::uint32_t max_latency_cycles;  // worst tick -> DMA-complete time
};
extern Stats g_stats;

// Configures TIM2, DMA1 Stream0 (I2C1_RX) and the NVIC. Requires i2c::init() and
// a configured sensor.
void init();
// Starts the periodic acquisition (timer enable).
void start();
// Call from the main loop: UART streaming + transaction watchdog.
void poll();

}  // namespace daq
