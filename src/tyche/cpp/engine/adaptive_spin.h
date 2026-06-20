#pragma once

// AdaptiveSpin -- adaptive spin/yield/sleep strategy for low-latency worker loops.
//
// Replaces condition_variable::wait_for() with a tiered waiting strategy:
//   1. Spin loop (cpu_pause) for low latency when work arrives soon
//   2. Thread yield after spin threshold exceeded
//   3. Sleep for configurable microseconds after yield threshold exceeded
//
// Platform-specific pause intrinsics:
//   - Windows x86/x64: _mm_pause() (MSVC intrinsic)
//   - Linux x86/x64:   __builtin_ia32_pause() (GCC/Clang)
//   - Linux ARM:       __asm__ __volatile__("yield" :::)

#include <atomic>
#include <cstdint>
#include <thread>
#include <chrono>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

namespace tyche {

class AdaptiveSpin {
public:
    explicit AdaptiveSpin(int spin_threshold = 1000,
                          int yield_threshold = 10000,
                          int sleep_us = 10) noexcept
        : _spin_threshold(spin_threshold)
        , _yield_threshold(yield_threshold)
        , _sleep_us(sleep_us) {}

    // Call when work was found. Resets idle counter.
    void reset() noexcept {
        _idle_count = 0;
    }

    // Call when no work was found. Performs appropriate wait.
    void wait() noexcept {
        ++_idle_count;
        if (_idle_count < _spin_threshold) {
            // Phase 1: spin with cpu pause
            cpu_pause();
        } else if (_idle_count < _yield_threshold) {
            // Phase 2: yield to other threads
            std::this_thread::yield();
        } else {
            // Phase 3: brief sleep to reduce CPU usage
            std::this_thread::sleep_for(std::chrono::microseconds(_sleep_us));
        }
    }

    int idle_count() const noexcept { return _idle_count; }

private:
    int _idle_count = 0;
    int _spin_threshold;
    int _yield_threshold;
    int _sleep_us;

    static inline void cpu_pause() noexcept {
#if defined(_MSC_VER)
        _mm_pause();
#elif defined(__x86_64__) || defined(__i386__)
        __builtin_ia32_pause();
#elif defined(__aarch64__) || defined(__arm__)
        __asm__ __volatile__("yield" :::);
#else
        // Fallback: no-op
#endif
    }
};

} // namespace tyche
