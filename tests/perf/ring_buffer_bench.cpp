// Microbenchmark for tyche::RingBuffer throughput and latency.
//
// Measures:
//   1. SPSC throughput (single-producer single-consumer)
//   2. MPSC throughput with 1, 2, 4, 8 producers
//   3. Baseline std::queue + std::mutex throughput
//   4. Latency distribution (p50, p99, p999) for push+pop round-trip

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <mutex>
#include <numeric>
#include <queue>
#include <string>
#include <thread>
#include <vector>

#include "tyche/cpp/engine/ring_buffer.h"

using Clock = std::chrono::high_resolution_clock;
using Nanos = std::chrono::nanoseconds;

// ---------------------------------------------------------------------------
// Baseline: std::queue protected by std::mutex
// ---------------------------------------------------------------------------
template <typename T>
class MutexQueue {
public:
    explicit MutexQueue(size_t capacity) : _capacity(capacity) {}

    bool try_push(T item) {
        std::lock_guard<std::mutex> lk(_mtx);
        if (_q.size() >= _capacity) return false;
        _q.push(std::move(item));
        return true;
    }

    std::optional<T> pop() {
        std::lock_guard<std::mutex> lk(_mtx);
        if (_q.empty()) return std::nullopt;
        T val = std::move(_q.front());
        _q.pop();
        return val;
    }

private:
    size_t _capacity;
    std::mutex _mtx;
    std::queue<T> _q;
};

// ---------------------------------------------------------------------------
// Benchmark result helpers
// ---------------------------------------------------------------------------
struct BenchResult {
    std::string name;
    double throughput_mops = 0.0;  // millions of ops/sec
    uint64_t total_ops = 0;
    double duration_sec = 0.0;
};

struct LatencyResult {
    std::string name;
    double p50_ns = 0.0;
    double p99_ns = 0.0;
    double p999_ns = 0.0;
};

static std::vector<BenchResult> g_throughput_results;
static std::vector<LatencyResult> g_latency_results;

static double percentile(const std::vector<double>& sorted, double p) {
    if (sorted.empty()) return 0.0;
    size_t idx = static_cast<size_t>(std::ceil(p * sorted.size())) - 1;
    if (idx >= sorted.size()) idx = sorted.size() - 1;
    return sorted[idx];
}

// ---------------------------------------------------------------------------
// 1 & 2. Throughput benchmark (RingBuffer)
// ---------------------------------------------------------------------------
template <typename Queue>
static BenchResult bench_throughput(const std::string& name,
                                    size_t capacity,
                                    int num_producers,
                                    double min_seconds) {
    Queue q(capacity);
    std::atomic<uint64_t> pushed{0};
    std::atomic<uint64_t> popped{0};
    std::atomic<bool> start_flag{false};
    std::atomic<bool> stop_flag{false};

    std::vector<std::thread> producers;
    producers.reserve(num_producers);

    for (int p = 0; p < num_producers; ++p) {
        producers.emplace_back([&] {
            int val = 0;
            while (!start_flag.load(std::memory_order_acquire))
                ;
            while (!stop_flag.load(std::memory_order_acquire)) {
                if (q.try_push(val++)) {
                    pushed.fetch_add(1, std::memory_order_relaxed);
                }
            }
        });
    }

    std::thread consumer([&] {
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto v = q.pop();
            if (v.has_value()) {
                popped.fetch_add(1, std::memory_order_relaxed);
            }
        }
        // Drain remaining items so producers can exit cleanly
        while (true) {
            auto v = q.pop();
            if (!v.has_value()) break;
            popped.fetch_add(1, std::memory_order_relaxed);
        }
    });

    // Warm-up
    start_flag.store(true, std::memory_order_release);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // Measure
    pushed.store(0, std::memory_order_relaxed);
    popped.store(0, std::memory_order_relaxed);

    auto t0 = Clock::now();
    auto t1 = t0;
    do {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        t1 = Clock::now();
    } while (std::chrono::duration<double>(t1 - t0).count() < min_seconds);

    stop_flag.store(true, std::memory_order_release);

    for (auto& t : producers) t.join();
    consumer.join();

    uint64_t total_popped = popped.load(std::memory_order_relaxed);
    double dur = std::chrono::duration<double>(t1 - t0).count();
    double mops = static_cast<double>(total_popped) / dur / 1'000'000.0;

    return BenchResult{name, mops, total_popped, dur};
}

// ---------------------------------------------------------------------------
// 3. Baseline: std::queue + mutex (SPSC only; MPSC would be even worse)
// ---------------------------------------------------------------------------
static BenchResult bench_mutex_queue(size_t capacity, double min_seconds) {
    MutexQueue<int> q(capacity);
    std::atomic<uint64_t> pushed{0};
    std::atomic<uint64_t> popped{0};
    std::atomic<bool> start_flag{false};
    std::atomic<bool> stop_flag{false};

    std::thread producer([&] {
        int val = 0;
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            if (q.try_push(val++)) {
                pushed.fetch_add(1, std::memory_order_relaxed);
            }
        }
    });

    std::thread consumer([&] {
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto v = q.pop();
            if (v.has_value()) {
                popped.fetch_add(1, std::memory_order_relaxed);
            }
        }
        while (true) {
            auto v = q.pop();
            if (!v.has_value()) break;
            popped.fetch_add(1, std::memory_order_relaxed);
        }
    });

    start_flag.store(true, std::memory_order_release);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    pushed.store(0, std::memory_order_relaxed);
    popped.store(0, std::memory_order_relaxed);

    auto t0 = Clock::now();
    auto t1 = t0;
    do {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        t1 = Clock::now();
    } while (std::chrono::duration<double>(t1 - t0).count() < min_seconds);

    stop_flag.store(true, std::memory_order_release);
    producer.join();
    consumer.join();

    uint64_t total_popped = popped.load(std::memory_order_relaxed);
    double dur = std::chrono::duration<double>(t1 - t0).count();
    double mops = static_cast<double>(total_popped) / dur / 1'000'000.0;

    return BenchResult{"mutex_queue_spsc", mops, total_popped, dur};
}

// ---------------------------------------------------------------------------
// 4. Latency benchmark: push+pop round-trip (ping-pong)
//
// Producer pushes one item, consumer pops it and pushes it back,
// producer pops it back.  Measures full round-trip time.
// ---------------------------------------------------------------------------
static LatencyResult bench_latency_ringbuffer(size_t capacity,
                                               double min_seconds) {
    tyche::RingBuffer<int> rb(capacity);
    std::atomic<bool> start_flag{false};
    std::atomic<bool> stop_flag{false};
    std::vector<double> latencies;
    latencies.reserve(10'000'000);

    std::thread producer([&] {
        int val = 0;
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto t0 = Clock::now();
            while (!stop_flag.load(std::memory_order_acquire)) {
                if (rb.try_push(val++)) break;
            }
            if (stop_flag.load(std::memory_order_acquire)) break;
            while (!stop_flag.load(std::memory_order_acquire)) {
                auto v = rb.pop();
                if (v.has_value()) break;
            }
            if (stop_flag.load(std::memory_order_acquire)) break;
            auto t1 = Clock::now();
            double ns = static_cast<double>(
                std::chrono::duration_cast<Nanos>(t1 - t0).count());
            latencies.push_back(ns);
        }
    });

    std::thread consumer([&] {
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto v = rb.pop();
            if (v.has_value()) {
                while (!stop_flag.load(std::memory_order_acquire)) {
                    if (rb.try_push(*v)) break;
                }
            }
        }
    });

    start_flag.store(true, std::memory_order_release);
    auto t0 = Clock::now();
    auto t1 = t0;
    do {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        t1 = Clock::now();
    } while (std::chrono::duration<double>(t1 - t0).count() < min_seconds);

    stop_flag.store(true, std::memory_order_release);
    producer.join();
    consumer.join();

    std::sort(latencies.begin(), latencies.end());
    return LatencyResult{
        "ringbuffer_spsc_latency",
        percentile(latencies, 0.50),
        percentile(latencies, 0.99),
        percentile(latencies, 0.999)};
}

static LatencyResult bench_latency_mutex_queue(size_t capacity,
                                                double min_seconds) {
    MutexQueue<int> q(capacity);
    std::atomic<bool> start_flag{false};
    std::atomic<bool> stop_flag{false};
    std::vector<double> latencies;
    latencies.reserve(10'000'000);

    std::thread producer([&] {
        int val = 0;
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto t0 = Clock::now();
            while (!stop_flag.load(std::memory_order_acquire)) {
                if (q.try_push(val++)) break;
            }
            if (stop_flag.load(std::memory_order_acquire)) break;
            while (!stop_flag.load(std::memory_order_acquire)) {
                auto v = q.pop();
                if (v.has_value()) break;
            }
            if (stop_flag.load(std::memory_order_acquire)) break;
            auto t1 = Clock::now();
            double ns = static_cast<double>(
                std::chrono::duration_cast<Nanos>(t1 - t0).count());
            latencies.push_back(ns);
        }
    });

    std::thread consumer([&] {
        while (!start_flag.load(std::memory_order_acquire))
            ;
        while (!stop_flag.load(std::memory_order_acquire)) {
            auto v = q.pop();
            if (v.has_value()) {
                while (!stop_flag.load(std::memory_order_acquire)) {
                    if (q.try_push(*v)) break;
                }
            }
        }
    });

    start_flag.store(true, std::memory_order_release);
    auto t0 = Clock::now();
    auto t1 = t0;
    do {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        t1 = Clock::now();
    } while (std::chrono::duration<double>(t1 - t0).count() < min_seconds);

    stop_flag.store(true, std::memory_order_release);
    producer.join();
    consumer.join();

    std::sort(latencies.begin(), latencies.end());
    return LatencyResult{
        "mutex_queue_spsc_latency",
        percentile(latencies, 0.50),
        percentile(latencies, 0.99),
        percentile(latencies, 0.999)};
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
int main(int argc, char* argv[]) {
    constexpr size_t CAPACITY = 1 << 20;  // 1M slots
    constexpr double MIN_SECONDS = 1.0;

    std::cout << "=== RingBuffer Microbenchmark ===\n";
    std::cout << "Capacity: " << CAPACITY << "\n";
    std::cout << "Min duration per test: " << MIN_SECONDS << " s\n\n";
    std::cout.flush();

    // --- Throughput: RingBuffer SPSC ---
    std::cout << "Running ringbuffer_spsc...\n";
    std::cout.flush();
    g_throughput_results.push_back(
        bench_throughput<tyche::RingBuffer<int>>(
            "ringbuffer_spsc", CAPACITY, 1, MIN_SECONDS));

    // --- Throughput: RingBuffer MPSC ---
    for (int producers : {2, 4, 8}) {
        std::cout << "Running ringbuffer_mpsc_" << producers << "p...\n";
        std::cout.flush();
        g_throughput_results.push_back(
            bench_throughput<tyche::RingBuffer<int>>(
                "ringbuffer_mpsc_" + std::to_string(producers) + "p",
                CAPACITY, producers, MIN_SECONDS));
    }

    // --- Throughput: MutexQueue SPSC baseline ---
    std::cout << "Running mutex_queue_spsc...\n";
    std::cout.flush();
    g_throughput_results.push_back(
        bench_mutex_queue(CAPACITY, MIN_SECONDS));

    // --- Latency ---
    std::cout << "Running ringbuffer_spsc_latency...\n";
    std::cout.flush();
    g_latency_results.push_back(
        bench_latency_ringbuffer(CAPACITY, MIN_SECONDS));

    std::cout << "Running mutex_queue_spsc_latency...\n";
    std::cout.flush();
    g_latency_results.push_back(
        bench_latency_mutex_queue(CAPACITY, MIN_SECONDS));

    // --- Output ---
    std::cout << "\n--- Throughput Results ---\n";
    for (const auto& r : g_throughput_results) {
        std::cout << r.name
                  << " throughput=" << r.throughput_mops << " Mops/s"
                  << " total_ops=" << r.total_ops
                  << " duration=" << r.duration_sec << " s\n";
    }

    std::cout << "\n--- Latency Results (push+pop round-trip, ns) ---\n";
    for (const auto& r : g_latency_results) {
        std::cout << r.name
                  << " p50=" << r.p50_ns
                  << " p99=" << r.p99_ns
                  << " p999=" << r.p999_ns << "\n";
    }

    std::cout << "\n=== Done ===\n";
    return 0;
}
