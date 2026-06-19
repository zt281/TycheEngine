// Benchmark: End-to-end latency distribution (CTP sim -> Engine -> Module).
//
// Measures the full pipeline latency with percentile distribution (p50/p99/p999).
// This is a micro-benchmark simulating the hot path without actual ZMQ sockets.

#include "tyche/cpp/engine/fast_clock.h"
#include "tyche/cpp/flat_message.h"
#include "tyche/cpp/flat_serializer.h"
#include "tyche/cpp/message.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>

namespace {

constexpr uint64_t kIterations = 500'000;

// Simulate a minimal engine-module hop: serialize + enqueue + deserialize
tyche::Message make_tick_message() {
    tyche::Message msg;
    msg.msg_type = tyche::MessageType::EVENT;
    msg.sender = "ctp_gateway";
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
std::vector<double> measure_latencies(Fn&& fn, uint64_t iterations) {
    std::vector<double> latencies;
    latencies.reserve(iterations);

    for (uint64_t i = 0; i < iterations; ++i) {
        auto t0 = std::chrono::high_resolution_clock::now();
        fn();
        auto t1 = std::chrono::high_resolution_clock::now();
        double ns = static_cast<double>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
        latencies.push_back(ns);
    }
    return latencies;
}

void print_percentiles(const std::vector<double>& latencies, const char* name) {
    std::vector<double> sorted = latencies;
    std::sort(sorted.begin(), sorted.end());

    auto pct = [&](double p) -> double {
        size_t idx = static_cast<size_t>(p * sorted.size());
        if (idx >= sorted.size()) idx = sorted.size() - 1;
        return sorted[idx];
    };

    double p50 = pct(0.50);
    double p99 = pct(0.99);
    double p999 = pct(0.999);
    double p9999 = pct(0.9999);
    double avg = 0.0;
    for (double v : sorted) avg += v;
    avg /= sorted.size();

    double min_v = sorted.front();
    double max_v = sorted.back();

    std::printf("\n=== %s ===\n", name);
    std::printf("  Samples : %zu\n", sorted.size());
    std::printf("  Min     : %.1f ns\n", min_v);
    std::printf("  Avg     : %.1f ns\n", avg);
    std::printf("  P50     : %.1f ns\n", p50);
    std::printf("  P99     : %.1f ns\n", p99);
    std::printf("  P99.9   : %.1f ns\n", p999);
    std::printf("  P99.99  : %.1f ns\n", p9999);
    std::printf("  Max     : %.1f ns\n", max_v);
}

}  // anonymous namespace

int main() {
    tyche::FastClock::calibrate();

    const tyche::Message tick_msg = make_tick_message();
    const std::vector<uint8_t> msgpack_ser = tyche::serialize(tick_msg);
    const tyche::FlatQuoteTick flat_tick = make_flat_quote();

    uint8_t flat_buffer[512];
    size_t flat_size = tyche::serialize_flat(tick_msg, flat_buffer, sizeof(flat_buffer));

    std::printf("E2E Latency Benchmark\n");
    std::printf("Iterations: %llu\n", static_cast<unsigned long long>(kIterations));
    std::printf("Msgpack size: %zu bytes\n", msgpack_ser.size());
    std::printf("FlatMessage size: %zu bytes\n", flat_size);
    std::printf("FlatQuoteTick size: %zu bytes\n", sizeof(tyche::FlatQuoteTickData));

    // 1. Full msgpack round-trip (simulates: serialize -> copy -> deserialize)
    auto lat_msgpack = measure_latencies(
        [&tick_msg]() {
            volatile auto buf = tyche::serialize(tick_msg);
            volatile auto msg = tyche::deserialize(buf.data(), buf.size());
            (void)msg;
        },
        kIterations);
    print_percentiles(lat_msgpack, "msgpack round-trip (serialize+deserialize)");

    // 2. FlatMessage round-trip
    auto lat_flat = measure_latencies(
        [&tick_msg, &flat_buffer]() {
            volatile size_t sz = tyche::serialize_flat(tick_msg, flat_buffer, sizeof(flat_buffer));
            volatile auto msg = tyche::deserialize_flat(flat_buffer, sz);
            (void)msg;
        },
        kIterations);
    print_percentiles(lat_flat, "FlatMessage round-trip");

    // 3. FlatQuoteTick zero-copy round-trip (memcpy + cast)
    alignas(64) uint8_t quote_buffer[128];
    auto lat_quote = measure_latencies(
        [&flat_tick, &quote_buffer]() {
            std::memcpy(quote_buffer, &flat_tick.data, sizeof(flat_tick.data));
            volatile auto ptr = reinterpret_cast<const tyche::FlatQuoteTickData*>(quote_buffer);
            (void)ptr;
        },
        kIterations);
    print_percentiles(lat_quote, "FlatQuoteTick memcpy+cast (zero-copy)");

    // 4. FastClock now() latency
    auto lat_clock = measure_latencies(
        []() {
            volatile double t = tyche::FastClock::now();
            (void)t;
        },
        kIterations);
    print_percentiles(lat_clock, "FastClock::now()");

    // 5. FastClock now_precise() latency
    auto lat_clock_precise = measure_latencies(
        []() {
            volatile double t = tyche::FastClock::now_precise();
            (void)t;
        },
        kIterations);
    print_percentiles(lat_clock_precise, "FastClock::now_precise()");

    std::printf("\n========== SUMMARY ==========\n");
    std::printf("%-45s %10s %10s %10s\n", "Path", "P50(ns)", "P99(ns)", "P99.9(ns)");
    std::printf("%-45s %10.1f %10.1f %10.1f\n", "msgpack round-trip",
                lat_msgpack[kIterations / 2], lat_msgpack[static_cast<size_t>(kIterations * 0.99)],
                lat_msgpack[static_cast<size_t>(kIterations * 0.999)]);
    std::printf("%-45s %10.1f %10.1f %10.1f\n", "FlatMessage round-trip",
                lat_flat[kIterations / 2], lat_flat[static_cast<size_t>(kIterations * 0.99)],
                lat_flat[static_cast<size_t>(kIterations * 0.999)]);
    std::printf("%-45s %10.1f %10.1f %10.1f\n", "FlatQuoteTick zero-copy",
                lat_quote[kIterations / 2], lat_quote[static_cast<size_t>(kIterations * 0.99)],
                lat_quote[static_cast<size_t>(kIterations * 0.999)]);

    return 0;
}
