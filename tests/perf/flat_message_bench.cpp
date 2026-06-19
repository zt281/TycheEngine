// Benchmark: FlatMessage serialize_flat / deserialize_flat vs msgpack.
//
// Measures zero-copy flat serialization overhead compared to msgpack.

#include "tyche/cpp/flat_message.h"
#include "tyche/cpp/flat_serializer.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr uint64_t kIterations = 1'000'000;

tyche::Message make_tick_message() {
    tyche::Message msg;
    msg.msg_type = tyche::MessageType::EVENT;
    msg.sender = "module_001";
    msg.event = "tick";
    msg.durability = tyche::DurabilityLevel::ASYNC_FLUSH;
    msg.payload["symbol"] = std::string("IF2506");
    msg.payload["bid"] = 3852.50;
    msg.payload["ask"] = 3853.00;
    msg.payload["last"] = 3852.75;
    msg.payload["volume"] = 142857;
    return msg;
}

tyche::FlatQuoteTick make_flat_quote() {
    tyche::FlatQuoteTick tick{};
    std::strncpy(tick.symbol(), "IF2506", sizeof(tick.data.symbol) - 1);
    tick.bid() = 3852.50;
    tick.ask() = 3853.00;
    tick.last() = 3852.75;
    tick.volume() = 142857;
    tick.timestamp() = 1717071234.567890;
    tick.local_ts() = 1717071234.700000;
    tick.tick_count() = 12345;
    tick.flags() = 0x01;
    return tick;
}

template <typename Fn>
struct BenchResult {
    double avg_ns;
    double msg_per_sec;
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
    double msg_per_sec = static_cast<double>(iterations) / total_sec;

    std::printf("\n=== %s ===\n", name);
    std::printf("  Iterations  : %llu\n", static_cast<unsigned long long>(iterations));
    std::printf("  Total time  : %.6f s\n", total_sec);
    std::printf("  Avg latency : %.3f ns/op\n", avg_ns);
    std::printf("  Throughput  : %.3f M msg/s\n", msg_per_sec / 1e6);
    return {avg_ns, msg_per_sec, total_sec};
}

}  // anonymous namespace

int main() {
    const tyche::Message tick_msg = make_tick_message();
    const std::vector<uint8_t> msgpack_ser = tyche::serialize(tick_msg);
    const tyche::FlatQuoteTick flat_tick = make_flat_quote();

    uint8_t flat_buffer[512];
    size_t flat_size = tyche::serialize_flat(tick_msg, flat_buffer, sizeof(flat_buffer));

    std::printf("MessagePack size : %zu bytes\n", msgpack_ser.size());
    std::printf("FlatMessage size : %zu bytes\n", flat_size);
    std::printf("FlatQuoteTick size: %zu bytes\n", sizeof(tyche::FlatQuoteTickData));

    // 1. msgpack serialize
    auto r_msgpack_ser = run_benchmark(
        "1. msgpack serialize()",
        [&tick_msg]() {
            volatile auto buf = tyche::serialize(tick_msg);
            (void)buf;
        },
        kIterations);

    // 2. flat serialize
    auto r_flat_ser = run_benchmark(
        "2. flat serialize_flat()",
        [&tick_msg, &flat_buffer]() {
            volatile size_t sz = tyche::serialize_flat(tick_msg, flat_buffer, sizeof(flat_buffer));
            (void)sz;
        },
        kIterations);

    // 3. msgpack deserialize
    auto r_msgpack_deser = run_benchmark(
        "3. msgpack deserialize()",
        [&msgpack_ser]() {
            volatile auto msg = tyche::deserialize(msgpack_ser.data(), msgpack_ser.size());
            (void)msg;
        },
        kIterations);

    // 4. flat deserialize
    auto r_flat_deser = run_benchmark(
        "4. flat deserialize_flat()",
        [&flat_buffer, flat_size]() {
            volatile auto msg = tyche::deserialize_flat(flat_buffer, flat_size);
            (void)msg;
        },
        kIterations);

    // 5. FlatQuoteTick serialize_flat_quote
    auto r_flat_quote_ser = run_benchmark(
        "5. serialize_flat_quote()",
        [&flat_tick, &flat_buffer]() {
            volatile size_t sz = tyche::serialize_flat_quote(
                flat_tick, flat_buffer, sizeof(flat_buffer));
            (void)sz;
        },
        kIterations);

    // 6. FlatQuoteTick deserialize_flat_quote (zero-copy cast)
    auto r_flat_quote_deser = run_benchmark(
        "6. deserialize_flat_quote() (zero-copy cast)",
        [&flat_buffer]() {
            volatile auto ptr = tyche::deserialize_flat_quote(flat_buffer, sizeof(tyche::FlatQuoteTickData));
            (void)ptr;
        },
        kIterations);

    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-40s %12s %15s\n", "Benchmark", "ns/op", "M msg/s");
    std::printf("%-40s %12.3f %15.3f\n", "1. msgpack serialize", r_msgpack_ser.avg_ns, r_msgpack_ser.msg_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "2. flat serialize", r_flat_ser.avg_ns, r_flat_ser.msg_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "3. msgpack deserialize", r_msgpack_deser.avg_ns, r_msgpack_deser.msg_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "4. flat deserialize", r_flat_deser.avg_ns, r_flat_deser.msg_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "5. serialize_flat_quote", r_flat_quote_ser.avg_ns, r_flat_quote_ser.msg_per_sec / 1e6);
    std::printf("%-40s %12.3f %15.3f\n", "6. deserialize_flat_quote", r_flat_quote_deser.avg_ns, r_flat_quote_deser.msg_per_sec / 1e6);

    std::printf("\nSpeedup vs msgpack: serialize %.2fx, deserialize %.2fx\n",
                r_msgpack_ser.avg_ns / r_flat_ser.avg_ns,
                r_msgpack_deser.avg_ns / r_flat_deser.avg_ns);

    return 0;
}
