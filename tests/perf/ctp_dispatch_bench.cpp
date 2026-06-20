// Benchmark: CTP Gateway batch dispatch throughput.
//
// Measures the throughput improvement of batch popping + adaptive spin
// vs single-item popping + sleep.

#include "tyche/cpp/engine/adaptive_spin.h"
#include "tyche/cpp/engine/ring_buffer.h"
#include "tyche/cpp/flat_message.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>

namespace {

constexpr uint64_t kTotalTicks = 1'000'000;
constexpr size_t kBatchSize = 64;

struct Tick {
    char symbol[16];
    double bid;
    double ask;
    double last;
    int64_t volume;
    double timestamp;
};

tyche::FlatQuoteTick make_flat_quote(int seq) {
    tyche::FlatQuoteTick tick{};
    std::snprintf(tick.symbol(), 16, "IF%04d", seq % 10000);
    tick.bid() = 3852.50 + (seq % 100) * 0.01;
    tick.ask() = tick.bid() + 0.5;
    tick.last() = tick.bid() + 0.25;
    tick.volume() = 100000 + seq;
    tick.timestamp() = 1717071234.567890 + seq * 0.001;
    tick.local_ts() = tick.timestamp() + 0.0001;
    tick.tick_count() = static_cast<uint32_t>(seq);
    tick.flags() = 0x01;
    return tick;
}

template <typename Fn>
struct BenchResult {
    double avg_ns;
    double ticks_per_sec;
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
    double ticks_per_sec = static_cast<double>(iterations) / total_sec;

    std::printf("\n=== %s ===\n", name);
    std::printf("  Iterations  : %llu\n", static_cast<unsigned long long>(iterations));
    std::printf("  Total time  : %.6f s\n", total_sec);
    std::printf("  Avg latency : %.3f ns/tick\n", avg_ns);
    std::printf("  Throughput  : %.3f M ticks/s\n", ticks_per_sec / 1e6);
    return {avg_ns, ticks_per_sec, total_sec};
}

}  // anonymous namespace

int main() {
    std::printf("CTP Gateway Batch Dispatch Benchmark\n");
    std::printf("Total ticks: %llu\n", static_cast<unsigned long long>(kTotalTicks));
    std::printf("Batch size : %zu\n", kBatchSize);

    // Pre-populate a ring buffer with ticks
    tyche::RingBuffer<tyche::FlatQuoteTick> rb(65536);
    for (uint64_t i = 0; i < kTotalTicks; ++i) {
        rb.push(make_flat_quote(static_cast<int>(i)));
    }

    // 1. Single-item pop (simulating old behavior)
    auto r_single = run_benchmark(
        "1. Single-item pop (old)",
        [&rb]() {
            auto tick = rb.pop();
            (void)tick;
        },
        kTotalTicks);

    // Re-populate
    for (uint64_t i = 0; i < kTotalTicks; ++i) {
        rb.push(make_flat_quote(static_cast<int>(i)));
    }

    // 2. Batch pop (simulating new behavior)
    auto r_batch = run_benchmark(
        "2. Batch pop (new, batch=64)",
        [&rb]() {
            tyche::FlatQuoteTick batch[kBatchSize];
            size_t n = 0;
            while (n < kBatchSize) {
                auto tick = rb.pop();
                if (!tick.has_value()) break;
                batch[n++] = std::move(*tick);
            }
            (void)n;
        },
        kTotalTicks / kBatchSize);

    // 3. AdaptiveSpin wait latency
    tyche::AdaptiveSpin spinner(1000, 10000, 10);
    auto r_spin = run_benchmark(
        "3. AdaptiveSpin::wait() (idle)",
        [&spinner]() {
            spinner.wait();
        },
        100'000);

    // 4. Batch pop + process (realistic)
    tyche::RingBuffer<tyche::FlatQuoteTick> rb2(65536);
    for (uint64_t i = 0; i < kTotalTicks; ++i) {
        rb2.push(make_flat_quote(static_cast<int>(i)));
    }

    alignas(64) uint8_t send_buffer[128];
    auto r_batch_process = run_benchmark(
        "4. Batch pop + serialize_flat_quote",
        [&rb2, &send_buffer]() {
            tyche::FlatQuoteTick batch[kBatchSize];
            size_t n = 0;
            while (n < kBatchSize) {
                auto tick = rb2.pop();
                if (!tick.has_value()) break;
                batch[n++] = std::move(*tick);
            }
            for (size_t i = 0; i < n; ++i) {
                std::memcpy(send_buffer, &batch[i].data, sizeof(batch[i].data));
            }
        },
        kTotalTicks / kBatchSize);

    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-45s %12s %15s\n", "Benchmark", "ns/tick", "M ticks/s");
    std::printf("%-45s %12.3f %15.3f\n", "1. Single-item pop", r_single.avg_ns, r_single.ticks_per_sec / 1e6);
    std::printf("%-45s %12.3f %15.3f\n", "2. Batch pop", r_batch.avg_ns * kBatchSize, r_batch.ticks_per_sec / 1e6);
    std::printf("%-45s %12.3f %15.3f\n", "3. AdaptiveSpin wait", r_spin.avg_ns, r_spin.ticks_per_sec / 1e6);
    std::printf("%-45s %12.3f %15.3f\n", "4. Batch + process", r_batch_process.avg_ns * kBatchSize, r_batch_process.ticks_per_sec / 1e6);

    std::printf("\nBatch speedup vs single-item: %.2fx\n",
                r_single.avg_ns / (r_batch.avg_ns * kBatchSize));

    return 0;
}
