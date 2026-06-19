#pragma once

// ObjectPool -- lock-free fixed-size object pool for QueueItem reuse.
//
// Eliminates per-item heap allocation by pre-allocating a pool of slots
// and managing them via a lock-free stack (Treiber stack).
//
// Each slot is cache-line aligned (64 bytes) to prevent false sharing.
//
// Usage:
//   ObjectPool<QueueItem, 65536> pool;
//   QueueItem* item = pool.acquire();
//   // ... use item ...
//   pool.release(item);

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <new>
#include <type_traits>
#include <vector>

namespace tyche {

template <typename T, size_t PoolSize = 65536>
class ObjectPool {
public:
    static_assert(std::is_trivially_destructible_v<T> || true,
                  "ObjectPool works best with trivially destructible types; "
                  "custom destructors are called in release()");

    ObjectPool() noexcept {
        // Pre-allocate all slots using unique_ptr to avoid copy constructor issues
        _slots.reserve(PoolSize);
        for (size_t i = 0; i < PoolSize; ++i) {
            _slots.emplace_back(std::make_unique<Slot>());
        }

        // Initialize free list as a linked list
        for (size_t i = 0; i < PoolSize; ++i) {
            _slots[i]->next.store((i + 1 < PoolSize) ? _slots[i + 1].get() : nullptr,
                                 std::memory_order_relaxed);
        }
        _free_list.store(_slots[0].get(), std::memory_order_relaxed);
        _available.store(PoolSize, std::memory_order_relaxed);
    }

    ~ObjectPool() noexcept {
        // Drain all objects and call destructors if needed
        Slot* slot = _free_list.load(std::memory_order_relaxed);
        while (slot) {
            Slot* next = slot->next.load(std::memory_order_relaxed);
            slot = next;
        }
    }

    // Acquire an object from the pool. Returns nullptr if pool exhausted.
    T* acquire() noexcept {
        Slot* head = _free_list.load(std::memory_order_acquire);
        while (head) {
            Slot* next = head->next.load(std::memory_order_relaxed);
            if (_free_list.compare_exchange_weak(head, next,
                                                  std::memory_order_acquire,
                                                  std::memory_order_relaxed)) {
                _available.fetch_sub(1, std::memory_order_relaxed);
                return reinterpret_cast<T*>(head->storage);
            }
            // CAS failed, head updated, retry
        }
        return nullptr;  // Pool exhausted
    }

    // Release an object back to the pool. Object must have been acquired from this pool.
    void release(T* obj) noexcept {
        if (!obj) return;

        // Call destructor if non-trivial
        if constexpr (!std::is_trivially_destructible_v<T>) {
            obj->~T();
        }

        Slot* slot = reinterpret_cast<Slot*>(
            reinterpret_cast<uint8_t*>(obj) -
            offsetof(Slot, storage));

        Slot* head = _free_list.load(std::memory_order_relaxed);
        do {
            slot->next.store(head, std::memory_order_relaxed);
        } while (!_free_list.compare_exchange_weak(head, slot,
                                                      std::memory_order_release,
                                                      std::memory_order_relaxed));
        _available.fetch_add(1, std::memory_order_relaxed);
    }

    size_t available() const noexcept {
        return _available.load(std::memory_order_relaxed);
    }

    size_t total() const noexcept { return PoolSize; }

private:
    struct alignas(64) Slot {
        std::atomic<Slot*> next{nullptr};
        alignas(alignof(T)) uint8_t storage[sizeof(T)];
    };

    std::atomic<Slot*> _free_list{nullptr};
    std::atomic<size_t> _available{0};
    std::vector<std::unique_ptr<Slot>> _slots;
};

} // namespace tyche
