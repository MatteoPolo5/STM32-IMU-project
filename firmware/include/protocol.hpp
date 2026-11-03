// Binary frame format streamed over the UART. See docs/protocol.md.
//
//  offset  size  field
//  ------  ----  ---------------------------------------------------------
//     0     2    sync          0xA5 0x5A
//     2     4    seq           sample counter, increments on EVERY timer tick
//     6     4    t_tick        DWT->CYCCNT captured at timer-interrupt entry
//    10     4    t_done        DWT->CYCCNT captured when the I2C DMA finished
//    14     2    dropped       cumulative lost samples (wraps at 65536)
//    16    14    raw           MPU6050 registers 0x3B..0x48, big-endian as read:
//                              ax ay az temp gx gy gz (int16 each)
//    30     2    crc16         CRC-16/CCITT-FALSE over bytes 2..29
//
// All multi-byte header fields are little-endian. The payload is left in the
// sensor's own byte order so the MCU never has to touch it.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace protocol {

inline constexpr std::size_t kFrameSize = 32;
inline constexpr std::size_t kPayloadSize = 14;
inline constexpr std::uint8_t kSync0 = 0xA5;
inline constexpr std::uint8_t kSync1 = 0x5A;

struct Sample {
  std::uint32_t seq = 0;
  std::uint32_t t_tick = 0;
  std::uint32_t t_done = 0;
  std::uint16_t dropped = 0;
  std::array<std::uint8_t, kPayloadSize> raw{};
};

namespace detail {
constexpr std::array<std::uint16_t, 256> make_crc_table() {
  std::array<std::uint16_t, 256> table{};
  for (std::uint32_t i = 0; i < 256; ++i) {
    auto crc = static_cast<std::uint16_t>(i << 8);
    for (int bit = 0; bit < 8; ++bit) {
      crc = static_cast<std::uint16_t>((crc & 0x8000U) ? ((crc << 1) ^ 0x1021U) : (crc << 1));
    }
    table[i] = crc;
  }
  return table;
}
inline constexpr auto kCrcTable = make_crc_table();
}  // namespace detail

// CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final XOR.
constexpr std::uint16_t crc16(const std::uint8_t* data, std::size_t len, std::uint16_t crc = 0xFFFF) {
  for (std::size_t i = 0; i < len; ++i) {
    crc = static_cast<std::uint16_t>((crc << 8) ^ detail::kCrcTable[(crc >> 8) ^ data[i]]);
  }
  return crc;
}

// Standard check value: CRC-16/CCITT-FALSE("123456789") == 0x29B1.
constexpr bool crc16_self_test() {
  constexpr std::uint8_t kCheck[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  return crc16(kCheck, sizeof(kCheck)) == 0x29B1;
}
static_assert(crc16_self_test(), "CRC-16/CCITT-FALSE implementation is wrong");

namespace detail {
inline void put_le16(std::uint8_t* p, std::uint16_t v) {
  p[0] = static_cast<std::uint8_t>(v);
  p[1] = static_cast<std::uint8_t>(v >> 8);
}
inline void put_le32(std::uint8_t* p, std::uint32_t v) {
  p[0] = static_cast<std::uint8_t>(v);
  p[1] = static_cast<std::uint8_t>(v >> 8);
  p[2] = static_cast<std::uint8_t>(v >> 16);
  p[3] = static_cast<std::uint8_t>(v >> 24);
}
}  // namespace detail

// Serialises one sample into exactly kFrameSize bytes at `out`.
inline void pack_frame(const Sample& s, std::uint8_t* out) {
  out[0] = kSync0;
  out[1] = kSync1;
  detail::put_le32(out + 2, s.seq);
  detail::put_le32(out + 6, s.t_tick);
  detail::put_le32(out + 10, s.t_done);
  detail::put_le16(out + 14, s.dropped);
  for (std::size_t i = 0; i < kPayloadSize; ++i) out[16 + i] = s.raw[i];
  detail::put_le16(out + 30, crc16(out + 2, 28));
}

}  // namespace protocol
