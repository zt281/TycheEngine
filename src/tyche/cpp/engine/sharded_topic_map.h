#pragma once

// OPT-2: Lock-free topic queue lookup with shard hashing
//
// Replaces the global std::mutex + unordered_map for topic queues with a
// fixed-size sharded hash table. Each bucket has its own spinlock, so
// concurrent operations on different topics hash to different buckets and
// proceed without contention.
//
// Hot path (_enqueue_from_xsub):
//   - Hash topic -> bucket index (bitmask, no division)
//   - Lock bucket spinlock -> find/insert -> unlock
//   - No global mutex, no shared_mutex, no atomic pointer CAS loops
//
// Registration / GC / admin paths:
//   - Same bucket lock granularity; concurrent ops on different buckets
//     proceed in parallel.

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "tyche/cpp/engine/topic_queue.h"

namespace tyche {

/// Fixed-size sharded map from topic string -> shared_ptr<TopicQueue>.
/// Bucket count is a power of two so hash % bucket_count becomes a bitmask.
class ShardedTopicQueueMap {
public:
    /// Default 256 buckets — tune with benchmarking if needed.
    explicit ShardedTopicQueueMap(size_t bucket_count = 256);

    /// Get or create a TopicQueue for the given topic.
    /// This is the hot-path used by _enqueue_from_xsub.
    /// @return shared_ptr to the queue (never null)
    std::shared_ptr<TopicQueue> get_or_create(
        const std::string& topic,
        size_t queue_capacity,
        double* out_last_access = nullptr);

    /// Find an existing queue without creating one.
    /// @return shared_ptr if found, nullptr otherwise
    std::shared_ptr<TopicQueue> find(const std::string& topic) const;

    /// Remove a topic queue. Used by GC (monitor worker).
    void erase(const std::string& topic);

    /// Snapshot all (topic, queue) pairs. Used by egress / admin.
    std::vector<std::pair<std::string, std::shared_ptr<TopicQueue>>> snapshot() const;

    /// Update last-access timestamp for a topic. Used by event egress.
    void touch(const std::string& topic, double now);

    /// Get last-access timestamp for a topic. Returns 0.0 if topic unknown.
    double last_access(const std::string& topic) const;

    /// Number of topic queues stored.
    size_t size() const;

private:
    struct Bucket {
        /// Simple test-and-test-and-set spinlock.
        /// We expect very low contention per bucket (different topics rarely
        /// collide, and same-topic ops are serialised by the event proxy).
        mutable std::atomic<bool> lock{false};

        std::vector<std::pair<std::string, std::shared_ptr<TopicQueue>>> entries;
        std::vector<std::pair<std::string, double>> last_access_times;

        void acquire() const noexcept {
            // Spin until we acquire the lock
            while (true) {
                // Test-and-test-and-set: first check without atomic exchange
                if (!lock.load(std::memory_order_relaxed)) {
                    if (!lock.exchange(true, std::memory_order_acquire)) {
                        return;
                    }
                }
                // Brief pause to reduce cache-line contention
#if defined(_MSC_VER)
                _mm_pause();
#else
                __builtin_ia32_pause();
#endif
            }
        }

        void release() const noexcept {
            lock.store(false, std::memory_order_release);
        }
    };

    const size_t _bucket_count;
    const size_t _bucket_mask;  // bucket_count - 1, for fast modulo
    std::unique_ptr<Bucket[]> _buckets;

    size_t _bucket_index(const std::string& topic) const noexcept;
};

}  // namespace tyche
