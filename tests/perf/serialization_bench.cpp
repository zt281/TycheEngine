// Microbenchmark: Message serialization / deserialization throughput.
//
// Measures:
//   1. serialize() throughput for a typical HFT tick message
//   2. deserialize() throughput for the same message
//   3. Full round-trip: serialize then deserialize
//   4. Raw struct memcpy baseline (flat binary format)
//   5. Msgpack overhead ratio
//
// Build (from project root):
//   mkdir -p build && cd build
//   cmake .. -DCMAKE_BUILD_TYPE=Release
//   cmake --build . --target serialization_bench
//
// Run:
//   ./bin/serialization_bench

#include "tyche/cpp/message.h"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr uint64_t kIterations = 1'000'000;

// ── Typical HFT tick message (small payload) ─────────────────────────

tyche::Message make_tick_message() {
    tyche::Message msg;
    msg.msg_type = tyche::MessageType::EVENT;
    msg.sender = "module_001";
    msg.event = "tick";
    msg.durability = tyche::DurabilityLevel::ASYNC_FLUSH;

    // 5 numeric fields typical of a market tick
    msg.payload["symbol"] = std::string("IF2506");
    msg.payload["bid"] = 3852.50;
    msg.payload["ask"] = 3853.00;
    msg.payload["last"] = 3852.75;
    msg.payload["volume"] = 142857;
    msg.payload["ts"] = 1717071234.567890;

    return msg;
}

// ── Flat binary baseline struct ──────────────────────────────────────

#pragma pack(push, 1)
struct FlatTick {
    char symbol[16];
    double bid;
    double ask;
    double last;
    int64_t volume;
    double ts;
};
#pragma pack(pop)

static_assert(sizeof(FlatTick) == 56, "FlatTick size mismatch");

FlatTick make_flat_tick() {
    FlatTick t{};
    std::strncpy(t.symbol, "IF2506", sizeof(t.symbol) - 1);
    t.bid = 3852.50;
    t.ask = 3853.00;
    t.last = 3852.75;
    t.volume = 142857;
    t.ts = 1717071234.567890;
    return t;
}

// ── Benchmark helpers ────────────────────────────────────────────────

template <typename Fn>
struct BenchResult {
    double avg_ns;      // average latency per op
    double msg_per_sec; // messages / second
    double bytes_per_sec;
    double total_sec;
};

template <typename Fn>
BenchResult<Fn> run_benchmark(const char* name,
                              Fn&& fn,
                              uint64_t iterations,
                              size_t bytes_per_msg) {
    // Warm-up
    for (uint64_t i = 0; i < iterations / 10; ++i) {
        fn();
    }

    auto t0 = std::chrono::high_resolution_clock::now();
    for (uint64_t i = 0; i < iterations; ++i) {
        fn();
    }
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    double total_sec = total_ns / 1e9;
    double avg_ns = total_ns / static_cast<double>(iterations);
    double msg_per_sec = static_cast<double>(iterations) / total_sec;
    double bytes_per_sec = msg_per_sec * static_cast<double>(bytes_per_msg);

    std::printf("\n=== %s ===\n", name);
    std::printf("  Iterations    : %llu\n", static_cast<unsigned long long>(iterations));
    std::printf("  Total time    : %.6f s\n", total_sec);
    std::printf("  Avg latency   : %.3f ns/op\n", avg_ns);
    std::printf("  Throughput    : %.3f M msg/s\n", msg_per_sec / 1e6);
    std::printf("  Bytes/sec     : %.3f MB/s\n", bytes_per_sec / 1e6);

    return {avg_ns, msg_per_sec, bytes_per_sec, total_sec};
}

}  // anonymous namespace

// ── main ─────────────────────────────────────────────────────────────

int main() {
    // Enable thousands separator in printf (POSIX; best-effort on Windows)
#ifdef _WIN32
    // Nothing portable here; just use raw numbers
#endif

    const tyche::Message tick_msg = make_tick_message();
    const std::vector<uint8_t> serialized = tyche::serialize(tick_msg);
    const size_t msgpack_size = serialized.size();

    const FlatTick flat_tick = make_flat_tick();
    constexpr size_t flat_size = sizeof(FlatTick);

    std::printf("MessagePack serialized size : %zu bytes\n", msgpack_size);
    std::printf("Flat binary struct size     : %zu bytes\n", flat_size);
    std::printf("Msgpack overhead ratio      : %.2fx\n",
                static_cast<double>(msgpack_size) / static_cast<double>(flat_size));
    std::printf("Iterations per benchmark    : %llu\n",
                static_cast<unsigned long long>(kIterations));

    // 1. serialize() throughput
    auto r_ser = run_benchmark(
        "1. serialize()",
        [&tick_msg]() {
            volatile auto buf = tyche::serialize(tick_msg);
            (void)buf;
        },
        kIterations,
        msgpack_size);

    // 2. deserialize() throughput
    auto r_deser = run_benchmark(
        "2. deserialize()",
        [&serialized]() {
            volatile auto msg = tyche::deserialize(serialized.data(), serialized.size());
            (void)msg;
        },
        kIterations,
        msgpack_size);

    // 3. Round-trip: serialize + deserialize
    auto r_rt = run_benchmark(
        "3. Round-trip (serialize + deserialize)",
        [&tick_msg]() {
            auto buf = tyche::serialize(tick_msg);
            volatile auto msg = tyche::deserialize(buf.data(), buf.size());
            (void)msg;
        },
        kIterations,
        msgpack_size);

    // 4. Flat binary baseline: memcpy
    alignas(64) char flat_dst[sizeof(FlatTick)];
    auto r_flat = run_benchmark(
        "4. Flat binary baseline (memcpy)",
        [&flat_tick, &flat_dst]() {
            std::memcpy(flat_dst, &flat_tick, sizeof(FlatTick));
            volatile char c = flat_dst[0];
            (void)c;
        },
        kIterations,
        flat_size);

    // 5. Summary
    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-40s %12s %15s %15s\n",
                "Benchmark", "ns/op", "M msg/s", "MB/s");
    std::printf("%-40s %12.3f %15.3f %15.3f\n",
                "1. serialize()", r_ser.avg_ns, r_ser.msg_per_sec / 1e6,
                r_ser.bytes_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f %15.3f\n",
                "2. deserialize()", r_deser.avg_ns, r_deser.msg_per_sec / 1e6,
                r_deser.bytes_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f %15.3f\n",
                "3. round-trip", r_rt.avg_ns, r_rt.msg_per_sec / 1e6,
                r_rt.bytes_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f %15.3f\n",
                "4. flat binary (memcpy)", r_flat.avg_ns, r_flat.msg_per_sec / 1e6,
                r_flat.bytes_per_sec / 1e6);
    std::printf("\nMsgpack overhead vs flat binary: %.2fx size, "
                "serialize %.2fx slower, deserialize %.2fx slower\n",
                static_cast<double>(msgpack_size) / static_cast<double>(flat_size),
                r_ser.avg_ns / r_flat.avg_ns,
                r_deser.avg_ns / r_flat.avg_ns);

    return 0;
}
