#pragma once

// RcuSnapshot -- Read-Copy-Update snapshot for subscription tables.
//
// Replaces shared_mutex-protected maps with atomic shared_ptr snapshots,
// enabling lock-free reads on the hot path (event egress, job routing).
//
// Write path (registration/unregistration) uses copy-on-write:
//   1. Load current snapshot
//   2. Copy and modify
//   3. Atomic replace
//
// Read path (hot):
//   auto snap = snapshot.load(std::memory_order_acquire);
//   // use snap->topic_subscribers, etc. without any lock
//
// NOTE: Old snapshots are kept alive by shared_ptr refcounting; they are
// freed when the last reader drops its reference. This is safe because
// the snapshot is only read, never modified in-place.

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "tyche/cpp/string_intern.h"

namespace tyche {

struct SubscriptionSnapshot {
    // topic_id -> subscriber module_ids
    std::unordered_map<InternId, std::vector<std::string>> topic_subscribers;
    // topic_id -> producer module_ids
    std::unordered_map<InternId, std::vector<std::string>> topic_producers;
    // topic_id -> handler module_ids (for job routing)
    std::unordered_map<InternId, std::vector<std::string>> job_handlers;
    // module_id -> availability map (topic -> available)
    std::unordered_map<std::string, std::unordered_map<std::string, bool>> module_availability;
    // module_id -> unavailable handler topics
    std::unordered_map<std::string, std::unordered_set<std::string>> unavailable_handlers;

    // Deep copy helper
    std::shared_ptr<SubscriptionSnapshot> clone() const {
        auto copy = std::make_shared<SubscriptionSnapshot>();
        copy->topic_subscribers = topic_subscribers;
        copy->topic_producers = topic_producers;
        copy->job_handlers = job_handlers;
        copy->module_availability = module_availability;
        copy->unavailable_handlers = unavailable_handlers;
        return copy;
    }
};

class RcuSnapshot {
public:
    RcuSnapshot() = default;

    // Load current snapshot (mutex-protected)
    std::shared_ptr<SubscriptionSnapshot> load() const noexcept {
        std::lock_guard<std::mutex> lock(_write_lock);
        return _snapshot;
    }

    // Store new snapshot (mutex-protected)
    void store(std::shared_ptr<SubscriptionSnapshot> snap) noexcept {
        std::lock_guard<std::mutex> lock(_write_lock);
        _snapshot = std::move(snap);
    }

    // Copy-on-write update: load -> clone -> modify -> store
    // Returns true if update succeeded (no concurrent modification detected)
    template <typename Func>
    bool update(Func&& modify_fn) {
        std::lock_guard<std::mutex> lock(_write_lock);
        auto current = _snapshot;
        auto next = current ? current->clone() : std::make_shared<SubscriptionSnapshot>();
        modify_fn(*next);
        _snapshot = std::move(next);
        return true;
    }

private:
    std::shared_ptr<SubscriptionSnapshot> _snapshot{nullptr};
    mutable std::mutex _write_lock;  // serializes writers and readers
};

} // namespace tyche
