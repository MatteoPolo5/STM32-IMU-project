#include <gtest/gtest.h>

#include <atomic>
#include <cstdint>
#include <thread>

#include "ring_buffer.hpp"

TEST(SpscRing, StartsEmpty) {
  SpscRing<int, 4> r;
  int v = 0;
  EXPECT_TRUE(r.empty());
  EXPECT_FALSE(r.pop(v));
}

TEST(SpscRing, FifoOrder) {
  SpscRing<int, 4> r;
  for (int i = 0; i < 4; ++i) EXPECT_TRUE(r.push(i));
  int v = -1;
  for (int i = 0; i < 4; ++i) {
    ASSERT_TRUE(r.pop(v));
    EXPECT_EQ(v, i);
  }
}

TEST(SpscRing, RejectsPushWhenFullAndKeepsContents) {
  SpscRing<int, 4> r;
  for (int i = 0; i < 4; ++i) ASSERT_TRUE(r.push(i));
  EXPECT_FALSE(r.push(99));
  EXPECT_EQ(r.size(), 4u);
  int v = 0;
  ASSERT_TRUE(r.pop(v));
  EXPECT_EQ(v, 0);
  EXPECT_TRUE(r.push(99));  // a slot is free again
}

TEST(SpscRing, SurvivesIndexWraparound) {
  SpscRing<std::uint32_t, 8> r;
  std::uint32_t v = 0;
  // Push/pop far more items than the capacity so the free-running indices wrap the buffer many times.
  for (std::uint32_t i = 0; i < 100000; ++i) {
    ASSERT_TRUE(r.push(i));
    ASSERT_TRUE(r.pop(v));
    ASSERT_EQ(v, i);
  }
}

// Real concurrency: one producer thread, one consumer thread, 2 million items.
TEST(SpscRing, TwoThreadsKeepOrderAndLoseNothing) {
  constexpr std::uint32_t kItems = 2'000'000;
  SpscRing<std::uint32_t, 64> r;
  std::thread producer([&] {
    for (std::uint32_t i = 0; i < kItems;) {
      if (r.push(i)) ++i;
    }
  });
  std::uint32_t expected = 0;
  bool in_order = true;
  while (expected < kItems) {
    std::uint32_t v;
    if (r.pop(v)) {
      if (v != expected) in_order = false;
      ++expected;
    }
  }
  producer.join();
  EXPECT_TRUE(in_order);
  EXPECT_TRUE(r.empty());
}
