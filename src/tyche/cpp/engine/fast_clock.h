#pragma once

// FastClock -- RDTSC-based cached timestamp for low-latency time queries.
//
// Replaces system_clock::now() (~25 ns) with a cached atomic read (~3 ns).
// A background calibration thread updates the cached timestamp every 1ms.
//
// Platform support:
//   - Windows: QueryPerformanceCounter() for calibration, __rdtsc() for x86
//   - Linux:   clock_gettime(CLOCK_MONOTONIC) for calibration, __rdtsc() for x86
//   - ARM:     cntvct_el0 for precise path

#include <atomic>
#include <cstdint>
#include <thread>
#include <chrono>
#include <mutex>

namespace tyche {

class FastClock {
public:
    // Fast path: read cached timestamp (updated by background thread every 1ms).
    // Uses memory_order_relaxed; suitable for enqueue_time, TTL checks.
    static double now() noexcept {
        return _cached_ns.load(std::memory_order_relaxed) * 1e-9;
    }

    // Precise path: directly query system clock.
    // Slightly slower (~25 ns) but accurate.
    static double now_precise() noexcept {
        return _system_now_ns() * 1e-9;
    }

    // Start background calibration thread.
    static void start_calibration();

    // Stop background calibration thread.
    static void stop_calibration();

    // Force immediate calibration.
    static void calibrate() noexcept;

private:
    // Cached timestamp in nanoseconds (epoch relative to program start)
    static inline std::atomic<int64_t> _cached_ns{0};

    // Calibration thread control
    static inline std::atomic<bool> _calibration_running{false};
    static inline std::thread _calibration_thread;
    static inline std::mutex _calibration_mutex;

    // System-specific nanosecond query
    static int64_t _system_now_ns() noexcept;

    // Calibration loop
    static void _calibration_loop();
};

} // namespace tyche
