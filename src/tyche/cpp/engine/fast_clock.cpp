// FastClock implementation -- RDTSC-based cached timestamp.
//
// Platform-specific calibration:
//   - Windows: QueryPerformanceCounter() / QueryPerformanceFrequency()
//   - Linux:   clock_gettime(CLOCK_MONOTONIC)
//   - x86:     __rdtsc() for precise path
//   - ARM:     cntvct_el0 for precise path

#include "tyche/cpp/engine/fast_clock.h"

#include <cassert>
#include <cmath>

// Platform-specific headers
#if defined(_WIN32)
#include <windows.h>
#else
#include <time.h>
#endif

#if defined(__x86_64__) || defined(__i386__)
#include <intrin.h>
#elif defined(__aarch64__)
#include <arm_neon.h>
#endif

namespace tyche {

// ── System-specific nanosecond query ──────────────────────────────────

int64_t FastClock::_system_now_ns() noexcept {
#if defined(_WIN32)
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    // Convert to nanoseconds: count * 1e9 / freq
    // Use double intermediate to avoid overflow on high counter values
    return static_cast<int64_t>(
        static_cast<double>(count.QuadPart) * 1'000'000'000.0 /
        static_cast<double>(freq.QuadPart));
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1'000'000'000LL + ts.tv_nsec;
#endif
}

// ── RDTSC / ARM counter read ────────────────────────────────────────

static inline uint64_t read_tsc() noexcept {
#if defined(_WIN32) && (defined(__x86_64__) || defined(__i386__))
    return __rdtsc();
#elif defined(__x86_64__) || defined(__i386__)
    unsigned int lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return (static_cast<uint64_t>(hi) << 32) | lo;
#elif defined(__aarch64__)
    uint64_t cntvct;
    __asm__ __volatile__("mrs %0, cntvct_el0" : "=r"(cntvct));
    return cntvct;
#else
    // Fallback: return 0 (precise path will use system clock)
    return 0;
#endif
}

// ── Calibration loop ──────────────────────────────────────────────────

void FastClock::_calibration_loop() {
    constexpr int64_t CALIBRATION_INTERVAL_US = 1000;  // 1ms

    // Initial calibration: establish tsc_to_ns ratio
    uint64_t tsc0 = read_tsc();
    int64_t ns0 = _system_now_ns();

    // Spin for ~1ms to get a good sample
    int64_t ns1 = ns0;
    while (ns1 - ns0 < CALIBRATION_INTERVAL_US * 1000) {
        ns1 = _system_now_ns();
    }
    uint64_t tsc1 = read_tsc();

    int64_t ns_delta = ns1 - ns0;
    uint64_t tsc_delta = tsc1 - tsc0;

    // Cache the ratio: ns_per_tsc = ns_delta / tsc_delta
    // Store as a double for precise multiplication
    double ns_per_tsc = 1.0;
    if (tsc_delta > 0) {
        ns_per_tsc = static_cast<double>(ns_delta) / static_cast<double>(tsc_delta);
    }

    // Store in a static local for now_precise() access
    static double s_ns_per_tsc = ns_per_tsc;
    static uint64_t s_tsc_base = tsc1;
    static int64_t s_ns_base = ns1;

    // Update the cached timestamp every 1ms
    while (_calibration_running.load(std::memory_order_relaxed)) {
        int64_t ns = _system_now_ns();
        _cached_ns.store(ns, std::memory_order_relaxed);

        // Periodic re-calibration (every 100 iterations = 100ms)
        static int counter = 0;
        if (++counter >= 100) {
            counter = 0;
            uint64_t tsc = read_tsc();
            int64_t ns_now = _system_now_ns();
            uint64_t tsc_delta_new = tsc - s_tsc_base;
            int64_t ns_delta_new = ns_now - s_ns_base;
            if (tsc_delta_new > 0) {
                double new_ratio = static_cast<double>(ns_delta_new) /
                                   static_cast<double>(tsc_delta_new);
                // Only update if drift is reasonable (< 5%)
                if (std::abs(new_ratio - s_ns_per_tsc) / s_ns_per_tsc < 0.05) {
                    s_ns_per_tsc = new_ratio;
                    s_tsc_base = tsc;
                    s_ns_base = ns_now;
                }
            }
        }

        // Sleep for 1ms
#if defined(_WIN32)
        Sleep(1);
#else
        struct timespec ts;
        ts.tv_sec = 0;
        ts.tv_nsec = 1'000'000;  // 1ms
        nanosleep(&ts, nullptr);
#endif
    }
}

// ── Public API ────────────────────────────────────────────────────────

void FastClock::start_calibration() {
    bool expected = false;
    if (!_calibration_running.compare_exchange_strong(expected, true,
                                                      std::memory_order_release,
                                                      std::memory_order_relaxed)) {
        return;  // Already running
    }

    std::lock_guard<std::mutex> lock(_calibration_mutex);
    if (_calibration_thread.joinable()) {
        return;  // Already started
    }

    // Initial calibration
    calibrate();

    _calibration_thread = std::thread(_calibration_loop);
}

void FastClock::stop_calibration() {
    _calibration_running.store(false, std::memory_order_release);

    std::lock_guard<std::mutex> lock(_calibration_mutex);
    if (_calibration_thread.joinable()) {
        _calibration_thread.join();
    }
}

void FastClock::calibrate() noexcept {
    int64_t ns = _system_now_ns();
    _cached_ns.store(ns, std::memory_order_relaxed);
}

} // namespace tyche
