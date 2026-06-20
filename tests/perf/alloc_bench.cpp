// Benchmark: ObjectPool vs heap allocation for QueueItem.
//
// Measures allocation latency of ObjectPool acquire/release vs std::make_unique.

#include "tyche/cpp/engine/object_pool.h"
#include "tyche/cpp/engine/topic_queue.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>

namespace {

constexpr uint64_t kIterations = 1'000'000;

struct DummyItem {
    double enqueue_time = 0.0;
    std::vector<tyche::Frame> frames;
    DummyItem() = default;
    explicit DummyItem(double t) : enqueue_time(t) {}
};

template <typename Fn>
struct BenchResult {
    double avg_ns;
    double ops_per_sec;
    double total_sec;
};

template <typename Fn>
BenchResult<Fn> run_benchmark(const char* name, Fn&& fn, uint64_t iterations) {
    for (uint64_t i = 0; i < iterations / 10; ++i) fn();

    auto t0 = std::chrono::high_resolution_clock::now();
    for (uint64_t i = 0; i < iterations; ++i) {
        fn();
    }
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    double total_sec = total_ns / 1e9;
    double avg_ns = total_ns / static_cast<double>(iterations);
    double ops_per_sec = static_cast<double>(iterations) / total_sec;

    std::printf("\n=== %s ===\n", name);
    std::printf("  Iterations : %llu\n", static_cast<unsigned long long>(iterations));
    std::printf("  Total time : %.6f s\n", total_sec);
    std::printf("  Avg latency: %.3f ns/op\n", avg_ns);
    std::printf("  Throughput : %.3f M ops/s\n", ops_per_sec / 1e6);
    return {avg_ns, ops_per_sec, total_sec};
}

}  // anonymous namespace

int main() {
    tyche::ObjectPool<DummyItem, 65536> pool;

    std::printf("Pool total slots: %zu\n", pool.total());
    std::printf("Pool available  : %zu\n", pool.available());

    // 1. ObjectPool acquire + release
    auto r_pool = run_benchmark(
        "1. ObjectPool acquire + release",
        [&pool]() {
            DummyItem* item = pool.acquire();
            if (item) {
                item->enqueue_time = 123.456;
                pool.release(item);
            }
        },
        kIterations);

    // 2. std::make_unique + destroy
    auto r_heap = run_benchmark(
        "2. std::make_unique + destroy",
        []() {
            auto item = std::make_unique<DummyItem>(123.456);
            item->frames.emplace_back();
            (void)item;
        },
        kIterations);

    // 3. ObjectPool with frame construction (realistic)
    auto r_pool_real = run_benchmark(
        "3. ObjectPool + Frame construction",
        [&pool]() {
            DummyItem* item = pool.acquire();
            if (item) {
                item->enqueue_time = 123.456;
                item->frames.clear();
                item->frames.emplace_back(reinterpret_cast<const uint8_t*>("test"), 4);
                pool.release(item);
            }
        },
        kIterations);

    // 4. Heap with frame construction
    auto r_heap_real = run_benchmark(
        "4. Heap + Frame construction",
        []() {
            auto item = std::make_unique<DummyItem>(123.456);
            item->frames.emplace_back(reinterpret_cast<const uint8_t*>("test"), 4);
            (void)item;
        },
        kIterations);

    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-40s %12s %15s\n", "Benchmark", "ns/op", "M ops/s");
    std::printf("%-40s %12.3f %15.3f\n", "1. ObjectPool", r_pool.avg_ns, r_pool.ops_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "2. Heap (make_unique)", r_heap.avg_ns, r_heap.ops_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "3. ObjectPool + frames", r_pool_real.avg_ns, r_pool_real.ops_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "4. Heap + frames", r_heap_real.avg_ns, r_heap_real.ops_per_sec / 1e6);

    std::printf("\nSpeedup: ObjectPool vs heap = %.2fx (simple), %.2fx (with frames)\n",
                r_heap.avg_ns / r_pool.avg_ns,
                r_heap_real.avg_ns / r_pool_real.avg_ns);

    return 0;
}
