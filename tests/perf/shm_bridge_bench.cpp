// Benchmark: SharedMemoryQueue bridge raw vs msgpack injection latency.
//
// Measures the overhead of forwarding raw bytes vs full msgpack serialization.

#include "tyche/cpp/engine/shared_memory_queue.h"
#include "tyche/cpp/message.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr uint64_t kIterations = 1'000'000;

struct FlatTick {
    char symbol[16];
    double bid;
    double ask;
    double last;
    int64_t volume;
    double ts;
};

tyche::Message make_tick_message() {
    tyche::Message msg;
    msg.msg_type = tyche::MessageType::EVENT;
    msg.sender = "shm_module";
    msg.event = "tick";
    msg.payload["symbol"] = std::string("IF2506");
    msg.payload["bid"] = 3852.50;
    msg.payload["ask"] = 3853.00;
    msg.payload["last"] = 3852.75;
    msg.payload["volume"] = 142857;
    return msg;
}

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
    const tyche::Message tick_msg = make_tick_message();
    const std::vector<uint8_t> msgpack_ser = tyche::serialize(tick_msg);

    FlatTick flat_tick{};
    std::strncpy(flat_tick.symbol, "IF2506", sizeof(flat_tick.symbol) - 1);
    flat_tick.bid = 3852.50;
    flat_tick.ask = 3853.00;
    flat_tick.last = 3852.75;
    flat_tick.volume = 142857;
    flat_tick.ts = 1717071234.567890;

    std::printf("Msgpack serialized size: %zu bytes\n", msgpack_ser.size());
    std::printf("Flat struct size      : %zu bytes\n", sizeof(FlatTick));

    // 1. msgpack serialize (simulating SHM bridge msgpack path)
    auto r_msgpack = run_benchmark(
        "1. msgpack serialize (SHM bridge overhead)",
        [&tick_msg]() {
            volatile auto buf = tyche::serialize(tick_msg);
            (void)buf;
        },
        kIterations);

    // 2. raw memcpy (simulating SHM bridge raw path)
    alignas(64) uint8_t raw_buffer[256];
    auto r_raw = run_benchmark(
        "2. raw memcpy (SHM bridge zero-copy)",
        [&flat_tick, &raw_buffer]() {
            std::memcpy(raw_buffer, &flat_tick, sizeof(FlatTick));
            volatile size_t sz = sizeof(FlatTick);
            (void)sz;
        },
        kIterations);

    // 3. TLS serialize (no heap allocation)
    auto r_tls = run_benchmark(
        "3. serialize_tls (no heap alloc)",
        [&tick_msg]() {
            volatile auto view = tyche::serialize_tls(tick_msg);
            (void)view;
        },
        kIterations);

    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-40s %12s %15s\n", "Benchmark", "ns/op", "M ops/s");
    std::printf("%-40s %12.3f %15.3f\n", "1. msgpack serialize", r_msgpack.avg_ns, r_msgpack.ops_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "2. raw memcpy", r_raw.avg_ns, r_raw.ops_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "3. serialize_tls", r_tls.avg_ns, r_tls.ops_per_sec / 1e6);

    std::printf("\nSHM bridge speedup: raw vs msgpack = %.2fx\n",
                r_msgpack.avg_ns / r_raw.avg_ns);
    std::printf("TLS vs heap serialize speedup = %.2fx\n",
                r_msgpack.avg_ns / r_tls.avg_ns);

    return 0;
}
