#pragma once

// TopicQueueIndex -- O(1) array-based index for InternId -> TopicQueue* lookup.
//
// Complements ShardedTopicQueueMap (which handles cold paths like creation,
// GC, and admin queries) with a fast, lock-free read path for hot paths:
//   - _enqueue_from_xsub:  lookup queue by InternId
//   - event_egress_worker: snapshot all (id, queue) pairs
//
// Write path (set) is synchronized by a mutex since it only happens at
// module registration time (cold path).

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <utility>
#include <vector>

#include "tyche/cpp/string_intern.h"
#include "tyche/cpp/engine/topic_queue.h"

namespace tyche {

class TopicQueueIndex {
public:
    TopicQueueIndex() = default;

    // Get queue by InternId. Returns nullptr if not found.
    // Read-locked; suitable for hot paths.
    TopicQueue* get(InternId id) const noexcept {
        std::shared_lock<std::shared_mutex> lock(_resize_lock);
        auto snapshot = _queues;
        if (!snapshot || id >= snapshot->size()) {
            return nullptr;
        }
        return (*snapshot)[id];
    }

    // Register a queue for an InternId. Thread-safe (used at registration time).
    void set(InternId id, TopicQueue* q) noexcept {
        std::unique_lock<std::shared_mutex> lock(_resize_lock);

        auto old_snapshot = _queues;
        size_t needed_size = static_cast<size_t>(id) + 1;

        std::shared_ptr<std::vector<TopicQueue*>> new_snapshot;
        if (old_snapshot && old_snapshot->size() >= needed_size) {
            // Reuse existing vector
            new_snapshot = std::make_shared<std::vector<TopicQueue*>>(*old_snapshot);
        } else {
            // Resize
            size_t new_size = old_snapshot ? old_snapshot->size() * 2 : 64;
            if (new_size < needed_size) new_size = needed_size;
            new_snapshot = std::make_shared<std::vector<TopicQueue*>>(new_size, nullptr);
            if (old_snapshot) {
                std::copy(old_snapshot->begin(), old_snapshot->end(), new_snapshot->begin());
            }
        }

        (*new_snapshot)[id] = q;
        _queues = std::move(new_snapshot);
    }

    // Snapshot all (id, queue) pairs for egress worker.
    // Returns only non-null entries.
    std::vector<std::pair<InternId, TopicQueue*>> snapshot() const {
        std::shared_lock<std::shared_mutex> lock(_resize_lock);
        auto ptr = _queues;
        if (!ptr) return {};

        std::vector<std::pair<InternId, TopicQueue*>> result;
        result.reserve(ptr->size() / 4);  // Approximate fill ratio
        for (size_t i = 0; i < ptr->size(); ++i) {
            if ((*ptr)[i]) {
                result.emplace_back(static_cast<InternId>(i), (*ptr)[i]);
            }
        }
        return result;
    }

private:
    // Shared_ptr to vector: read path uses shared_lock, write path uses unique_lock
    std::shared_ptr<std::vector<TopicQueue*>> _queues{nullptr};
    mutable std::shared_mutex _resize_lock;  // shared_lock for reads, unique_lock for writes
};

} // namespace tyche
