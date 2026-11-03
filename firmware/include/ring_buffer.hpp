// Lock-free single-producer / single-consumer ring buffer with static storage.
//
// Used to hand samples from the DMA-complete interrupt (producer) to the main
// loop (consumer) without disabling interrupts. No dynamic allocation.
//
// Correctness relies on exactly one producer context and one consumer context
// and on release/acquire ordering of the two indices. The indices are free
// running 32-bit counters; unsigned wrap-around keeps (head - tail) correct.
#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>

template <typename T, std::size_t N>
class SpscRing {
  static_assert(N >= 2 && (N & (N - 1)) == 0, "capacity must be a power of two");

 public:
  static constexpr std::size_t capacity() { return N; }

  // Producer side. Returns false (and stores nothing) when the ring is full.
  bool push(const T& value) {
    const std::uint32_t head = head_.load(std::memory_order_relaxed);
    const std::uint32_t tail = tail_.load(std::memory_order_acquire);
    if (head - tail >= N) return false;
    buf_[head & (N - 1)] = value;
    head_.store(head + 1, std::memory_order_release);
    return true;
  }

  // Consumer side. Returns false when the ring is empty.
  bool pop(T& out) {
    const std::uint32_t tail = tail_.load(std::memory_order_relaxed);
    const std::uint32_t head = head_.load(std::memory_order_acquire);
    if (head == tail) return false;
    out = buf_[tail & (N - 1)];
    tail_.store(tail + 1, std::memory_order_release);
    return true;
  }

  std::size_t size() const {
    return head_.load(std::memory_order_acquire) - tail_.load(std::memory_order_acquire);
  }
  bool empty() const { return size() == 0; }

 private:
  T buf_[N]{};
  std::atomic<std::uint32_t> head_{0};  // next slot to write (producer)
  std::atomic<std::uint32_t> tail_{0};  // next slot to read (consumer)
};
