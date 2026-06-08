// Microbenchmark for TopicQueue throughput and _enqueue_from_xsub pattern.
//
// Measures:
//   1. TopicQueue::put() throughput with DROP_OLDEST strategy
//   2. TopicQueue::get() throughput
//   3. Combined put+get throughput
//   4. Simulated _enqueue_from_xsub: string topic extraction + unordered_map lookup + queue put
//   5. Optimized version: pre-hashed topic key (uint64_t) + array-indexed queue lookup
//
// Build: add to tests/cpp/CMakeLists.txt as tyche_perf executable.

#include <chrono>
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "tyche/cpp/engine/topic_queue.h"

using namespace tyche;

// ── Benchmark harness ────────────────────────────────────────────────

struct BenchResult {
    double ops_per_sec = 0.0;
    uint64_t total_ops = 0;
    double elapsed_sec = 0.0;
};

template <typename F>
BenchResult benchmark_duration(F&& fn, double min_seconds = 1.0) {
    using clock = std::chrono::high_resolution_clock;
    uint64_t ops = 0;
    auto start = clock::now();
    auto end = start;
    do {
        fn(ops);
        end = clock::now();
    } while (std::chrono::duration<double>(end - start).count() < min_seconds);

    double elapsed = std::chrono::duration<double>(end - start).count();
    return {static_cast<double>(ops) / elapsed, ops, elapsed};
}

static void print_result(const char* name, const BenchResult& r) {
    std::printf("%-45s %12.3f ops/sec  (%10" PRIu64 " ops in %.3f s)\n",
                name, r.ops_per_sec, r.total_ops, r.elapsed_sec);
}

// ── Helpers ──────────────────────────────────────────────────────────

static QueueItem make_dummy_item() {
    std::vector<uint8_t> frame(64, 0xAB);
    return QueueItem(0.0, {frame});
}

static std::vector<uint8_t> make_dummy_frame(size_t sz = 64) {
    return std::vector<uint8_t>(sz, 0xAB);
}

// ── 1. put() throughput (DROP_OLDEST) ────────────────────────────────

static BenchResult bench_put_drop_oldest(size_t capacity) {
    TopicQueue q(capacity, BackpressureStrategy::DROP_OLDEST);
    auto item = make_dummy_item();
    return benchmark_duration([&](uint64_t& ops) {
        q.put(item);
        ++ops;
    });
}

// ── 2. get() throughput ──────────────────────────────────────────────

static BenchResult bench_get(size_t capacity) {
    TopicQueue q(capacity, BackpressureStrategy::DROP_OLDEST);
    auto item = make_dummy_item();
    // Pre-fill so get() never hits empty
    for (size_t i = 0; i < capacity; ++i) {
        q.put(item);
    }
    return benchmark_duration([&](uint64_t& ops) {
        auto result = q.get();
        (void)result;
        // Re-fill to keep the queue non-empty
        q.put(item);
        ++ops;
    });
}

// ── 3. Combined put+get throughput (single thread) ───────────────────

static BenchResult bench_put_get_combined(size_t capacity) {
    TopicQueue q(capacity, BackpressureStrategy::DROP_OLDEST);
    auto item = make_dummy_item();
    return benchmark_duration([&](uint64_t& ops) {
        q.put(item);
        auto result = q.get();
        (void)result;
        ++ops;
    });
}

// ── 4. Simulated _enqueue_from_xsub (string map) ─────────────────────

static BenchResult bench_enqueue_from_xsub_string_map(size_t num_topics) {
    // Pre-create topics and queues exactly like TycheEngine::_enqueue_from_xsub
    std::unordered_map<std::string, std::shared_ptr<TopicQueue>> topic_queues;
    std::vector<std::string> topics;
    topics.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        std::string t = "topic_" + std::to_string(i);
        topics.push_back(t);
        topic_queues[t] = std::make_shared<TopicQueue>(1024, BackpressureStrategy::DROP_OLDEST);
    }

    std::vector<std::vector<uint8_t>> frames = {make_dummy_frame(16), make_dummy_frame(64)};
    size_t idx = 0;

    return benchmark_duration([&](uint64_t& ops) {
        // Simulate topic extraction from first frame (bytes -> string)
        const std::string& topic = topics[idx % num_topics];
        idx++;

        // unordered_map lookup + create-if-missing (cold-path omitted for steady state)
        auto it = topic_queues.find(topic);
        if (it != topic_queues.end()) {
            it->second->put(QueueItem(0.0, frames));
        }
        ++ops;
    });
}

// ── 5. Optimized: pre-hashed uint64_t key + array-indexed lookup ─────

static BenchResult bench_enqueue_optimized_array(size_t num_topics) {
    // Pre-hashed topic keys mapped directly to an array of queues
    std::vector<std::unique_ptr<TopicQueue>> topic_queues;
    topic_queues.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        topic_queues.emplace_back(std::make_unique<TopicQueue>(1024, BackpressureStrategy::DROP_OLDEST));
    }

    std::vector<uint64_t> topic_keys;
    topic_keys.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        topic_keys.push_back(0xA5A5A5A5A5A5A5A5ULL ^ i);  // pseudo-hash
    }

    std::vector<std::vector<uint8_t>> frames = {make_dummy_frame(16), make_dummy_frame(64)};
    size_t idx = 0;

    return benchmark_duration([&](uint64_t& ops) {
        uint64_t key = topic_keys[idx % num_topics];
        idx++;
        size_t slot = static_cast<size_t>(key % num_topics);
        topic_queues[slot]->put(QueueItem(0.0, frames));
        ++ops;
    });
}

// ── 6. Baseline: map lookup only (no queue put) ──────────────────────

static BenchResult bench_string_map_lookup_only(size_t num_topics) {
    std::unordered_map<std::string, std::shared_ptr<TopicQueue>> topic_queues;
    std::vector<std::string> topics;
    topics.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        std::string t = "topic_" + std::to_string(i);
        topics.push_back(t);
        topic_queues[t] = std::make_shared<TopicQueue>(1024, BackpressureStrategy::DROP_OLDEST);
    }

    size_t idx = 0;
    return benchmark_duration([&](uint64_t& ops) {
        const std::string& topic = topics[idx % num_topics];
        idx++;
        volatile auto it = topic_queues.find(topic);
        (void)it;
        ++ops;
    });
}

// ── 7. Baseline: array index only (no queue put) ─────────────────────

static BenchResult bench_array_index_lookup_only(size_t num_topics) {
    std::vector<std::unique_ptr<TopicQueue>> topic_queues;
    topic_queues.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        topic_queues.emplace_back(std::make_unique<TopicQueue>(1024, BackpressureStrategy::DROP_OLDEST));
    }

    std::vector<uint64_t> topic_keys;
    topic_keys.reserve(num_topics);
    for (size_t i = 0; i < num_topics; ++i) {
        topic_keys.push_back(0xA5A5A5A5A5A5A5A5ULL ^ i);
    }

    size_t idx = 0;
    return benchmark_duration([&](uint64_t& ops) {
        uint64_t key = topic_keys[idx % num_topics];
        idx++;
        size_t slot = static_cast<size_t>(key % num_topics);
        volatile auto* ptr = topic_queues[slot].get();
        (void)ptr;
        ++ops;
    });
}

// ── Main ─────────────────────────────────────────────────────────────

int main() {
    constexpr size_t CAPACITY = 1024;
    constexpr size_t NUM_TOPICS = 256;

    std::printf("\n");
    std::printf("=============================================================\n");
    std::printf("  TopicQueue Microbenchmark                                   \n");
    std::printf("  Capacity: %zu    Topics: %zu    Min duration: 1.0 s each   \n",
                CAPACITY, NUM_TOPICS);
    std::printf("=============================================================\n\n");

    // --- Core queue ops ---
    std::printf("--- Core TopicQueue Operations ---\n");
    print_result("1. put() DROP_OLDEST", bench_put_drop_oldest(CAPACITY));
    print_result("2. get() (pre-filled)", bench_get(CAPACITY));
    print_result("3. put()+get() combined", bench_put_get_combined(CAPACITY));
    std::printf("\n");

    // --- Enqueue pattern simulation ---
    std::printf("--- _enqueue_from_xsub Pattern Simulation ---\n");
    auto r_string_full = bench_enqueue_from_xsub_string_map(NUM_TOPICS);
    auto r_array_full  = bench_enqueue_optimized_array(NUM_TOPICS);
    print_result("4. string topic + unordered_map lookup + put", r_string_full);
    print_result("5. uint64_t key + array index + put", r_array_full);
    std::printf("\n");

    // --- Lookup overhead isolation ---
    std::printf("--- Lookup Overhead (no queue put) ---\n");
    auto r_string_lookup = bench_string_map_lookup_only(NUM_TOPICS);
    auto r_array_lookup  = bench_array_index_lookup_only(NUM_TOPICS);
    print_result("6. string map lookup only", r_string_lookup);
    print_result("7. array index lookup only", r_array_lookup);
    std::printf("\n");

    // --- Summary / overhead analysis ---
    std::printf("--- Overhead Analysis ---\n");

    double map_lookup_overhead_ns = 1e9 / r_string_lookup.ops_per_sec;
    double array_lookup_overhead_ns = 1e9 / r_array_lookup.ops_per_sec;
    double string_map_overhead_ns   = 1e9 / r_string_full.ops_per_sec;
    double array_full_overhead_ns   = 1e9 / r_array_full.ops_per_sec;

    std::printf("String map lookup overhead:     %8.2f ns/op\n", map_lookup_overhead_ns);
    std::printf("Array index lookup overhead:    %8.2f ns/op\n", array_lookup_overhead_ns);
    std::printf("String map + put total:         %8.2f ns/op\n", string_map_overhead_ns);
    std::printf("Array index + put total:        %8.2f ns/op\n", array_full_overhead_ns);
    std::printf("\n");

    double speedup_full = r_array_full.ops_per_sec / r_string_full.ops_per_sec;
    double speedup_lookup = r_array_lookup.ops_per_sec / r_string_lookup.ops_per_sec;
    std::printf("Array vs String speedup (full path):  %.2fx\n", speedup_full);
    std::printf("Array vs String speedup (lookup only): %.2fx\n", speedup_lookup);
    std::printf("\n");

    if (r_string_lookup.ops_per_sec > 0 && r_array_lookup.ops_per_sec > 0) {
        double map_penalty_pct =
            (map_lookup_overhead_ns - array_lookup_overhead_ns) / map_lookup_overhead_ns * 100.0;
        std::printf("Map lookup is %.1f%% slower than array index (lookup only)\n", map_penalty_pct);
    }

    std::printf("\n=============================================================\n");
    return 0;
}
