#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <new>
#include <optional>
#include <vector>
#include <thread>

namespace tyche {

// Cache line size for padding to prevent false sharing
#ifdef __cpp_lib_hardware_interference_size
    inline constexpr size_t CACHE_LINE_SIZE = std::hardware_destructive_interference_size;
#else
    inline constexpr size_t CACHE_LINE_SIZE = 64;
#endif

/// Lock-free MPSC Ring Buffer.
///
/// Multiple producers can push concurrently using CAS on sequence numbers.
/// Single consumer pops items sequentially.
///
/// Capacity is rounded up to the next power of 2 for efficient modulo via bitmask.
template <typename T>
class RingBuffer {
public:
    explicit RingBuffer(size_t requested_capacity)
        : _mask(next_power_of_2(requested_capacity < 2 ? 2 : requested_capacity) - 1)
        , _write_pos(0)
        , _read_pos(0)
        , _slots(_mask + 1)
    {
        // Initialize each slot's sequence to its index
        for (size_t i = 0; i < _slots.size(); ++i) {
            _slots[i].sequence.store(i, std::memory_order_relaxed);
        }
    }

    // Non-copyable and non-movable
    RingBuffer(const RingBuffer&) = delete;
    RingBuffer& operator=(const RingBuffer&) = delete;
    RingBuffer(RingBuffer&&) = delete;
    RingBuffer& operator=(RingBuffer&&) = delete;

    /// Try to push an item (move). Returns false if buffer is full (DROP_NEWEST semantics).
    bool try_push(T&& item) {
        size_t pos = _write_pos.load(std::memory_order_relaxed);

        for (;;) {
            Slot& slot = _slots[pos & _mask];
            size_t seq = slot.sequence.load(std::memory_order_acquire);

            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos);

            if (diff == 0) {
                // Slot is available for writing; try to claim it
                if (_write_pos.compare_exchange_weak(pos, pos + 1,
                        std::memory_order_relaxed, std::memory_order_relaxed)) {
                    // Successfully claimed the slot
                    slot.data = std::move(item);
                    slot.sequence.store(pos + 1, std::memory_order_release);
                    return true;
                }
                // CAS failed, pos has been updated by compare_exchange_weak, retry
            } else if (diff < 0) {
                // Buffer is full
                return false;
            } else {
                // Another producer has moved write_pos ahead, reload
                pos = _write_pos.load(std::memory_order_relaxed);
            }
        }
    }

    /// Try to push an item (copy). Returns false if buffer is full (DROP_NEWEST semantics).
    bool try_push(const T& item) {
        size_t pos = _write_pos.load(std::memory_order_relaxed);

        for (;;) {
            Slot& slot = _slots[pos & _mask];
            size_t seq = slot.sequence.load(std::memory_order_acquire);

            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos);

            if (diff == 0) {
                if (_write_pos.compare_exchange_weak(pos, pos + 1,
                        std::memory_order_relaxed, std::memory_order_relaxed)) {
                    slot.data = item;
                    slot.sequence.store(pos + 1, std::memory_order_release);
                    return true;
                }
            } else if (diff < 0) {
                return false;
            } else {
                pos = _write_pos.load(std::memory_order_relaxed);
            }
        }
    }

    /// Push an item, overwriting the oldest entry if full (DROP_OLDEST semantics).
    /// NOTE: This is only safe when called from a single producer, or when the pop side
    /// is externally synchronized. In multi-producer scenarios, concurrent push_overwrite
    /// calls may race on advancing the read position.
    void push_overwrite(T&& item) {
        while (!try_push(std::move(item))) {
            // Buffer is full - advance read_pos to discard oldest entry
            size_t rpos = _read_pos.load(std::memory_order_relaxed);
            Slot& slot = _slots[rpos & _mask];
            size_t seq = slot.sequence.load(std::memory_order_acquire);

            intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(rpos + 1);

            if (diff == 0) {
                // Slot has data ready to be consumed; discard it
                if (_read_pos.compare_exchange_strong(rpos, rpos + 1,
                        std::memory_order_relaxed, std::memory_order_relaxed)) {
                    // Mark slot as available for writing again
                    slot.sequence.store(rpos + _mask + 1, std::memory_order_release);
                }
            }
            // Retry push regardless of whether discard succeeded
            // (another thread may have already consumed or discarded)
        }
    }

    /// Push an item, spinning/yielding until space is available (BLOCK_PRODUCER semantics).
    void push_blocking(T&& item) {
        while (!try_push(std::move(item))) {
            std::this_thread::yield();
        }
    }

    /// Alias for push_blocking for backward compatibility.
    void push(T&& item) {
        push_blocking(std::move(item));
    }

    /// Pop an item from the consumer side. Returns std::nullopt if empty.
    /// Must be called from a single consumer thread only.
    std::optional<T> pop() {
        size_t pos = _read_pos.load(std::memory_order_relaxed);
        Slot& slot = _slots[pos & _mask];
        size_t seq = slot.sequence.load(std::memory_order_acquire);

        intptr_t diff = static_cast<intptr_t>(seq) - static_cast<intptr_t>(pos + 1);

        if (diff == 0) {
            // Data is available
            T result = std::move(slot.data);
            // Mark slot as writable again: sequence = pos + capacity
            slot.sequence.store(pos + _mask + 1, std::memory_order_release);
            _read_pos.store(pos + 1, std::memory_order_relaxed);
            return result;
        }

        // No data available
        return std::nullopt;
    }

    /// Current number of items in the buffer (approximate for MPSC).
    size_t size() const noexcept {
        size_t w = _write_pos.load(std::memory_order_relaxed);
        size_t r = _read_pos.load(std::memory_order_relaxed);
        return w >= r ? w - r : 0;
    }

    /// Check if buffer is empty.
    bool empty() const noexcept {
        return size() == 0;
    }

    /// Check if buffer is full.
    bool full() const noexcept {
        return size() >= (_mask + 1);
    }

    /// Get capacity (always a power of 2).
    size_t capacity() const noexcept {
        return _mask + 1;
    }

private:
    size_t _mask;  // capacity - 1, for efficient modulo

    // Padded to separate cache lines to avoid false sharing
    alignas(CACHE_LINE_SIZE) std::atomic<size_t> _write_pos;
    alignas(CACHE_LINE_SIZE) std::atomic<size_t> _read_pos;

    // Slot structure with sequence number for MPSC coordination
    struct Slot {
        std::atomic<size_t> sequence;
        T data;

        Slot() : sequence(0), data() {}
    };

    std::vector<Slot> _slots;

    /// Round up to the next power of 2.
    static size_t next_power_of_2(size_t n) {
        if (n <= 1) return 1;
        n--;
        n |= n >> 1;
        n |= n >> 2;
        n |= n >> 4;
        n |= n >> 8;
        n |= n >> 16;
        n |= n >> 32;
        return n + 1;
    }
};

} // namespace tyche
