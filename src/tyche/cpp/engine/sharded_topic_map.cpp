#include "tyche/cpp/engine/sharded_topic_map.h"

#include <algorithm>
#include <numeric>

namespace tyche {

// ── Hash helper (FNV-1a 64-bit) ───────────────────────────────────────

static uint64_t fnv1a_64(const std::string& s) noexcept {
    uint64_t hash = 0xcbf29ce484222325ULL;
    for (unsigned char c : s) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 0x100000001b3ULL;
    }
    return hash;
}

// ── Constructor ───────────────────────────────────────────────────────

ShardedTopicQueueMap::ShardedTopicQueueMap(size_t bucket_count)
    : _bucket_count(bucket_count), _bucket_mask(bucket_count - 1) {
    // Ensure bucket_count is a power of two so mask works
    if ((bucket_count & _bucket_mask) != 0) {
        // Fallback: round up to next power of two
        size_t pow2 = 1;
        while (pow2 < bucket_count) pow2 <<= 1;
        const_cast<size_t&>(_bucket_count) = pow2;
        const_cast<size_t&>(_bucket_mask) = pow2 - 1;
    }
    _buckets = std::make_unique<Bucket[]>(_bucket_count);
}

// ── Bucket index ──────────────────────────────────────────────────────

size_t ShardedTopicQueueMap::_bucket_index(const std::string& topic) const noexcept {
    return static_cast<size_t>(fnv1a_64(topic)) & _bucket_mask;
}

// ── Get or create (hot path) ──────────────────────────────────────────

std::shared_ptr<TopicQueue> ShardedTopicQueueMap::get_or_create(
    const std::string& topic,
    size_t queue_capacity,
    double* out_last_access) {

    size_t idx = _bucket_index(topic);
    Bucket& bucket = _buckets[idx];

    bucket.acquire();

    // Search existing entry
    for (auto& [t, q] : bucket.entries) {
        if (t == topic) {
            if (out_last_access) {
                for (auto& [lt, la] : bucket.last_access_times) {
                    if (lt == topic) {
                        *out_last_access = la;
                        break;
                    }
                }
            }
            auto result = q;
            bucket.release();
            return result;
        }
    }

    // Create new queue
    auto q = std::make_shared<TopicQueue>(queue_capacity);
    bucket.entries.emplace_back(topic, q);
    bucket.last_access_times.emplace_back(topic, 0.0);

    if (out_last_access) {
        *out_last_access = 0.0;
    }

    bucket.release();
    return q;
}

// ── Find (read-only, no create) ───────────────────────────────────────

std::shared_ptr<TopicQueue> ShardedTopicQueueMap::find(const std::string& topic) const {
    size_t idx = _bucket_index(topic);
    const Bucket& bucket = _buckets[idx];

    bucket.acquire();
    for (const auto& [t, q] : bucket.entries) {
        if (t == topic) {
            auto result = q;
            bucket.release();
            return result;
        }
    }
    bucket.release();
    return nullptr;
}

// ── Get raw pointer (read-only, no create, no refcount) ─────────────────

TopicQueue* ShardedTopicQueueMap::get_raw(const std::string& topic) const {
    size_t idx = _bucket_index(topic);
    const Bucket& bucket = _buckets[idx];

    bucket.acquire();
    for (const auto& [t, q] : bucket.entries) {
        if (t == topic) {
            auto* result = q.get();
            bucket.release();
            return result;
        }
    }
    bucket.release();
    return nullptr;
}

// ── Erase (GC) ────────────────────────────────────────────────────────

void ShardedTopicQueueMap::erase(const std::string& topic) {
    size_t idx = _bucket_index(topic);
    Bucket& bucket = _buckets[idx];

    bucket.acquire();
    bucket.entries.erase(
        std::remove_if(bucket.entries.begin(), bucket.entries.end(),
            [&topic](const auto& p) { return p.first == topic; }),
        bucket.entries.end());
    bucket.last_access_times.erase(
        std::remove_if(bucket.last_access_times.begin(), bucket.last_access_times.end(),
            [&topic](const auto& p) { return p.first == topic; }),
        bucket.last_access_times.end());
    bucket.release();
}

// ── Snapshot ──────────────────────────────────────────────────────────

std::vector<std::pair<std::string, std::shared_ptr<TopicQueue>>> ShardedTopicQueueMap::snapshot() const {
    std::vector<std::pair<std::string, std::shared_ptr<TopicQueue>>> result;
    for (size_t i = 0; i < _bucket_count; ++i) {
        _buckets[i].acquire();
        for (const auto& [t, q] : _buckets[i].entries) {
            result.emplace_back(t, q);
        }
        _buckets[i].release();
    }
    return result;
}

// ── Touch (update last access time) ───────────────────────────────────

void ShardedTopicQueueMap::touch(const std::string& topic, double now) {
    size_t idx = _bucket_index(topic);
    Bucket& bucket = _buckets[idx];

    bucket.acquire();
    for (auto& [t, la] : bucket.last_access_times) {
        if (t == topic) {
            la = now;
            bucket.release();
            return;
        }
    }
    bucket.last_access_times.emplace_back(topic, now);
    bucket.release();
}

// ── Last access time lookup ───────────────────────────────────────────

double ShardedTopicQueueMap::last_access(const std::string& topic) const {
    size_t idx = _bucket_index(topic);
    const Bucket& bucket = _buckets[idx];

    bucket.acquire();
    for (const auto& [t, la] : bucket.last_access_times) {
        if (t == topic) {
            bucket.release();
            return la;
        }
    }
    bucket.release();
    return 0.0;
}

// ── Size ──────────────────────────────────────────────────────────────

size_t ShardedTopicQueueMap::size() const {
    size_t total = 0;
    for (size_t i = 0; i < _bucket_count; ++i) {
        _buckets[i].acquire();
        total += _buckets[i].entries.size();
        _buckets[i].release();
    }
    return total;
}

}  // namespace tyche
