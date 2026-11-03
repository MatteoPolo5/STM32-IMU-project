#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "protocol.hpp"

namespace {

std::vector<std::uint8_t> from_hex(const std::string& hex) {
  std::vector<std::uint8_t> out;
  for (std::size_t i = 0; i + 1 < hex.size(); i += 2) {
    out.push_back(static_cast<std::uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return out;
}

std::map<std::string, std::string> load_golden() {
  std::ifstream f(GOLDEN_VECTOR_FILE);
  EXPECT_TRUE(f.good()) << "cannot open " << GOLDEN_VECTOR_FILE;
  std::map<std::string, std::string> kv;
  std::string line;
  while (std::getline(f, line)) {
    if (line.empty() || line[0] == '#') continue;
    const auto eq = line.find('=');
    kv[line.substr(0, eq)] = line.substr(eq + 1);
  }
  return kv;
}

}  // namespace

TEST(Crc16, StandardCheckValue) {
  const std::uint8_t data[] = {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
  EXPECT_EQ(protocol::crc16(data, sizeof(data)), 0x29B1);
}

TEST(Crc16, EmptyInputReturnsInit) {
  EXPECT_EQ(protocol::crc16(nullptr, 0), 0xFFFF);
}

TEST(Crc16, DetectsEverySingleBitFlipInAFrame) {
  protocol::Sample s;
  s.seq = 42;
  std::uint8_t frame[protocol::kFrameSize];
  protocol::pack_frame(s, frame);
  const std::uint16_t good = protocol::crc16(frame + 2, 28);
  for (std::size_t byte = 2; byte < 30; ++byte) {
    for (int bit = 0; bit < 8; ++bit) {
      frame[byte] ^= static_cast<std::uint8_t>(1U << bit);
      EXPECT_NE(protocol::crc16(frame + 2, 28), good) << "byte " << byte << " bit " << bit;
      frame[byte] ^= static_cast<std::uint8_t>(1U << bit);
    }
  }
}

TEST(Frame, LayoutAndSize) {
  static_assert(protocol::kFrameSize == 32);
  protocol::Sample s;
  s.seq = 0x04030201;
  s.t_tick = 0x08070605;
  s.t_done = 0x0C0B0A09;
  s.dropped = 0x0E0D;
  for (std::size_t i = 0; i < protocol::kPayloadSize; ++i) s.raw[i] = static_cast<std::uint8_t>(0xA0 + i);
  std::uint8_t f[protocol::kFrameSize];
  protocol::pack_frame(s, f);
  EXPECT_EQ(f[0], 0xA5);
  EXPECT_EQ(f[1], 0x5A);
  EXPECT_EQ(f[2], 0x01);  // little-endian seq
  EXPECT_EQ(f[5], 0x04);
  EXPECT_EQ(f[6], 0x05);   // t_tick
  EXPECT_EQ(f[10], 0x09);  // t_done
  EXPECT_EQ(f[14], 0x0D);  // dropped
  EXPECT_EQ(f[15], 0x0E);
  EXPECT_EQ(f[16], 0xA0);  // payload start
  EXPECT_EQ(f[29], 0xAD);  // payload end
  const std::uint16_t crc = static_cast<std::uint16_t>(f[30] | (f[31] << 8));
  EXPECT_EQ(crc, protocol::crc16(f + 2, 28));
}

// The same vector is checked by tests/python/test_protocol.py: this is what
// guarantees that the firmware and the host tools agree on the wire format.
TEST(Frame, MatchesGoldenVectorFromPythonReference) {
  const auto kv = load_golden();
  protocol::Sample s;
  s.seq = static_cast<std::uint32_t>(std::stoul(kv.at("seq"), nullptr, 16));
  s.t_tick = static_cast<std::uint32_t>(std::stoul(kv.at("t_tick"), nullptr, 16));
  s.t_done = static_cast<std::uint32_t>(std::stoul(kv.at("t_done"), nullptr, 16));
  s.dropped = static_cast<std::uint16_t>(std::stoul(kv.at("dropped"), nullptr, 16));
  const auto raw = from_hex(kv.at("raw"));
  ASSERT_EQ(raw.size(), protocol::kPayloadSize);
  for (std::size_t i = 0; i < raw.size(); ++i) s.raw[i] = raw[i];

  const auto expected = from_hex(kv.at("frame"));
  ASSERT_EQ(expected.size(), protocol::kFrameSize);
  std::uint8_t f[protocol::kFrameSize];
  protocol::pack_frame(s, f);
  for (std::size_t i = 0; i < protocol::kFrameSize; ++i) EXPECT_EQ(f[i], expected[i]) << "byte " << i;
}
