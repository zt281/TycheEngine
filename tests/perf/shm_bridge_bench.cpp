// Benchmark: SharedMemoryQueue bridge raw vs msgpack injection latency.
//
// Measures the overhead of forwarding raw bytes vs full msgpack serialization.

#include "tyche/cpp/engine/shared_memory_queue.h"
#include "tyche/cpp/engine/adaptive_spin.h"
#include "tyche/cpp/message.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
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

    // ========================================================================
    // 4. read() vs read_into() — allocation overhead comparison
    // ========================================================================
    std::printf("\n\n============ P0/P1 OPTIMIZATION BENCHMARKS ============\n");

    {
        constexpr uint64_t kReadIter = 1'000'000;
        tyche::SharedMemoryQueue::Config cfg_alloc;
        cfg_alloc.name = "bench_read_alloc";
        cfg_alloc.slot_count = 1024;
        cfg_alloc.max_msg_size = 4096;

        tyche::SharedMemoryQueue q_alloc(cfg_alloc, true);
        std::vector<uint8_t> payload(128, 0x42);

        // Warm up
        for (uint64_t i = 0; i < kReadIter / 10; ++i) {
            q_alloc.write(payload.data(), payload.size());
            auto r = q_alloc.read();
            (void)r;
        }

        // Bench read() with heap allocation
        auto t0 = std::chrono::high_resolution_clock::now();
        for (uint64_t i = 0; i < kReadIter; ++i) {
            q_alloc.write(payload.data(), payload.size());
            auto r = q_alloc.read();
            (void)r;
        }
        auto t1 = std::chrono::high_resolution_clock::now();
        double ns_alloc = static_cast<double>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count()) /
            static_cast<double>(kReadIter);

        // Bench read_into() zero-allocation
        tyche::SharedMemoryQueue::Config cfg_into;
        cfg_into.name = "bench_read_into";
        cfg_into.slot_count = 1024;
        cfg_into.max_msg_size = 4096;

        tyche::SharedMemoryQueue q_into(cfg_into, true);
        uint8_t stack_buf[256];
        size_t out_size = 0;

        // Warm up
        for (uint64_t i = 0; i < kReadIter / 10; ++i) {
            q_into.write(payload.data(), payload.size());
            q_into.read_into(stack_buf, sizeof(stack_buf), out_size);
        }

        t0 = std::chrono::high_resolution_clock::now();
        for (uint64_t i = 0; i < kReadIter; ++i) {
            q_into.write(payload.data(), payload.size());
            q_into.read_into(stack_buf, sizeof(stack_buf), out_size);
        }
        t1 = std::chrono::high_resolution_clock::now();
        double ns_into = static_cast<double>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count()) /
            static_cast<double>(kReadIter);

        double speedup_read = ns_alloc / ns_into;
        std::printf("\n[bench] read_alloc:        %.1f ns/op (%llu iterations)\n",
                    ns_alloc, static_cast<unsigned long long>(kReadIter));
        std::printf("[bench] read_into:         %.1f ns/op (%llu iterations)  [speedup: %.2fx]\n",
                    ns_into, static_cast<unsigned long long>(kReadIter), speedup_read);
    }

    // ========================================================================
    // 5. adaptive_spin vs sleep(1ms) — wakeup latency comparison
    // ========================================================================
    {
        constexpr uint64_t kWakeupIter = 10'000;

        // Helper lambda to compute percentiles
        auto percentile = [](std::vector<int64_t>& sorted, double p) -> int64_t {
            if (sorted.empty()) return 0;
            size_t idx = static_cast<size_t>(p * static_cast<double>(sorted.size() - 1));
            return sorted[idx];
        };

        // --- bench_wakeup_sleep: uses sleep_for(1ms) polling ---
        {
            tyche::SharedMemoryQueue::Config cfg_sleep;
            cfg_sleep.name = "bench_wakeup_sleep";
            cfg_sleep.slot_count = 1024;
            cfg_sleep.max_msg_size = 4096;

            tyche::SharedMemoryQueue q_sleep(cfg_sleep, true);
            std::vector<uint8_t> payload(64, 0xAA);
            std::vector<int64_t> latencies;
            latencies.reserve(kWakeupIter);

            std::atomic<bool> stop_flag{false};
            std::atomic<int64_t> write_ts{0};

            // Reader thread: polls with sleep_for(1ms)
            std::thread reader([&]() {
                uint8_t buf[256];
                size_t out_sz = 0;
                while (!stop_flag.load(std::memory_order_relaxed)) {
                    if (q_sleep.read_into(buf, sizeof(buf), out_sz)) {
                        auto now = std::chrono::high_resolution_clock::now().time_since_epoch().count();
                        int64_t wts = write_ts.load(std::memory_order_acquire);
                        latencies.push_back(now - wts);
                    } else {
                        std::this_thread::sleep_for(std::chrono::milliseconds(1));
                    }
                }
            });

            // Writer: post messages with timestamp
            for (uint64_t i = 0; i < kWakeupIter; ++i) {
                auto now = std::chrono::high_resolution_clock::now().time_since_epoch().count();
                write_ts.store(now, std::memory_order_release);
                q_sleep.write(payload.data(), payload.size());
                // Wait for reader to consume before next write
                while (!q_sleep.empty()) {
                    std::this_thread::yield();
                }
            }

            stop_flag.store(true, std::memory_order_relaxed);
            reader.join();

            std::sort(latencies.begin(), latencies.end());
            double p50_us = static_cast<double>(percentile(latencies, 0.50)) / 1000.0;
            double p99_us = static_cast<double>(percentile(latencies, 0.99)) / 1000.0;
            double max_us = latencies.empty() ? 0.0 : static_cast<double>(latencies.back()) / 1000.0;
            std::printf("\n[bench] wakeup_sleep:      p50=%.1f\xC2\xB5s, p99=%.1f\xC2\xB5s, max=%.1f\xC2\xB5s\n",
                        p50_us, p99_us, max_us);

            // Store for speedup comparison
            double sleep_p50 = p50_us;
            double sleep_p99 = p99_us;

            // --- bench_wakeup_adaptive_spin: uses AdaptiveSpin ---
            tyche::SharedMemoryQueue::Config cfg_spin;
            cfg_spin.name = "bench_wakeup_spin";
            cfg_spin.slot_count = 1024;
            cfg_spin.max_msg_size = 4096;

            tyche::SharedMemoryQueue q_spin(cfg_spin, true);
            std::vector<int64_t> latencies_spin;
            latencies_spin.reserve(kWakeupIter);

            std::atomic<bool> stop_spin{false};
            std::atomic<int64_t> write_ts_spin{0};

            std::thread reader_spin([&]() {
                tyche::AdaptiveSpin spinner(1000, 10000, 10);
                uint8_t buf[256];
                size_t out_sz = 0;
                while (!stop_spin.load(std::memory_order_relaxed)) {
                    if (q_spin.read_into(buf, sizeof(buf), out_sz)) {
                        auto now = std::chrono::high_resolution_clock::now().time_since_epoch().count();
                        int64_t wts = write_ts_spin.load(std::memory_order_acquire);
                        latencies_spin.push_back(now - wts);
                        spinner.reset();
                    } else {
                        spinner.wait();
                    }
                }
            });

            for (uint64_t i = 0; i < kWakeupIter; ++i) {
                auto now = std::chrono::high_resolution_clock::now().time_since_epoch().count();
                write_ts_spin.store(now, std::memory_order_release);
                q_spin.write(payload.data(), payload.size());
                while (!q_spin.empty()) {
                    std::this_thread::yield();
                }
            }

            stop_spin.store(true, std::memory_order_relaxed);
            reader_spin.join();

            std::sort(latencies_spin.begin(), latencies_spin.end());
            double spin_p50 = static_cast<double>(percentile(latencies_spin, 0.50)) / 1000.0;
            double spin_p99 = static_cast<double>(percentile(latencies_spin, 0.99)) / 1000.0;
            double spin_max = latencies_spin.empty() ? 0.0 : static_cast<double>(latencies_spin.back()) / 1000.0;
            std::printf("[bench] wakeup_adaptive:   p50=%.1f\xC2\xB5s, p99=%.1f\xC2\xB5s, max=%.1f\xC2\xB5s  [speedup: p50=%.1fx, p99=%.1fx]\n",
                        spin_p50, spin_p99, spin_max,
                        sleep_p50 / (spin_p50 > 0 ? spin_p50 : 1.0),
                        sleep_p99 / (spin_p99 > 0 ? spin_p99 : 1.0));
        }
    }

    // ========================================================================
    // 6. mutex vs RCU snapshot — lock contention comparison (4 readers + 1 writer)
    // ========================================================================
    {
        constexpr int kReaderCount = 4;
        constexpr auto kDuration = std::chrono::seconds(2);
        constexpr int kVecSize = 64;  // simulating module list

        // --- Mutex-based version ---
        {
            std::shared_mutex mtx;
            std::vector<int> shared_vec(kVecSize, 1);
            std::atomic<uint64_t> total_reads{0};
            std::atomic<bool> stop_mtx{false};

            std::vector<std::thread> readers;
            for (int r = 0; r < kReaderCount; ++r) {
                readers.emplace_back([&]() {
                    uint64_t local_reads = 0;
                    while (!stop_mtx.load(std::memory_order_relaxed)) {
                        std::shared_lock<std::shared_mutex> lock(mtx);
                        volatile int sum = 0;
                        for (int v : shared_vec) {
                            sum += v;
                        }
                        (void)sum;
                        ++local_reads;
                    }
                    total_reads.fetch_add(local_reads, std::memory_order_relaxed);
                });
            }

            // Writer thread: occasional rebuilds
            std::thread writer_mtx([&]() {
                while (!stop_mtx.load(std::memory_order_relaxed)) {
                    {
                        std::unique_lock<std::shared_mutex> lock(mtx);
                        shared_vec.assign(kVecSize, static_cast<int>(shared_vec[0] + 1));
                    }
                    std::this_thread::sleep_for(std::chrono::microseconds(100));
                }
            });

            std::this_thread::sleep_for(kDuration);
            stop_mtx.store(true, std::memory_order_relaxed);

            writer_mtx.join();
            for (auto& t : readers) t.join();

            double mutex_reads_sec = static_cast<double>(total_reads.load()) /
                std::chrono::duration<double>(kDuration).count();
            std::printf("\n[bench] mutex_4r1w:        %.0f reads/sec\n", mutex_reads_sec);

            // --- RCU snapshot version (shared_ptr + atomic swap) ---
            auto rcu_data = std::make_shared<std::vector<int>>(kVecSize, 1);
            std::atomic<uint64_t> rcu_total_reads{0};
            std::atomic<bool> stop_rcu{false};

            // Atomic shared_ptr via mutex-guarded load/store (C++17 compatible)
            std::mutex rcu_ptr_mtx;
            auto rcu_load = [&]() -> std::shared_ptr<std::vector<int>> {
                std::lock_guard<std::mutex> lk(rcu_ptr_mtx);
                return rcu_data;
            };
            auto rcu_store = [&](std::shared_ptr<std::vector<int>> new_ptr) {
                std::lock_guard<std::mutex> lk(rcu_ptr_mtx);
                rcu_data = std::move(new_ptr);
            };

            std::vector<std::thread> rcu_readers;
            for (int r = 0; r < kReaderCount; ++r) {
                rcu_readers.emplace_back([&]() {
                    uint64_t local_reads = 0;
                    while (!stop_rcu.load(std::memory_order_relaxed)) {
                        auto snapshot = rcu_load();
                        volatile int sum = 0;
                        for (int v : *snapshot) {
                            sum += v;
                        }
                        (void)sum;
                        ++local_reads;
                    }
                    rcu_total_reads.fetch_add(local_reads, std::memory_order_relaxed);
                });
            }

            std::thread writer_rcu([&]() {
                int gen = 1;
                while (!stop_rcu.load(std::memory_order_relaxed)) {
                    auto new_vec = std::make_shared<std::vector<int>>(kVecSize, ++gen);
                    rcu_store(std::move(new_vec));
                    std::this_thread::sleep_for(std::chrono::microseconds(100));
                }
            });

            std::this_thread::sleep_for(kDuration);
            stop_rcu.store(true, std::memory_order_relaxed);

            writer_rcu.join();
            for (auto& t : rcu_readers) t.join();

            double rcu_reads_sec = static_cast<double>(rcu_total_reads.load()) /
                std::chrono::duration<double>(kDuration).count();
            double speedup_rcu = rcu_reads_sec / (mutex_reads_sec > 0 ? mutex_reads_sec : 1.0);
            std::printf("[bench] rcu_4r1w:          %.0f reads/sec  [speedup: %.2fx]\n",
                        rcu_reads_sec, speedup_rcu);
        }
    }

    std::printf("\n============ ALL BENCHMARKS COMPLETE ============\n");
    return 0;
}
