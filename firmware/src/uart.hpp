#pragma once

#include <cstddef>
#include <cstdint>

namespace uart {

// USART2 (PA2 = TX, routed to the ST-LINK virtual COM port) + DMA1 Stream6.
void init();

// Blocking helpers, only for boot messages before streaming starts.
void write(const char* s);
void write_dec(std::uint32_t v);
void write_hex8(std::uint8_t v);

// Non-blocking transmit through DMA. Returns false if a transfer is in flight.
// The buffer must stay untouched until tx_busy() returns false.
bool start_tx(const std::uint8_t* data, std::size_t len);
bool tx_busy();
std::uint32_t tx_errors();

}  // namespace uart
