// Unit tests for tyche::FastClock.
//
// Tests:
//   1. now() returns a reasonable timestamp
//   2. now_precise() returns a reasonable timestamp
//   3. now() and now_precise() are within 2ms of each other
//   4. Calibration thread starts and stops correctly
//   5. now() is monotonic (non-decreasing)

#include <gtest/gtest.h>

#include "tyche/cpp/engine/fast_clock.h"

#include <chrono>
#include <thread>

namespace tyche {
namespace {

TEST(FastClockTest, NowReturnsReasonableValue) {
    FastClock::calibrate();

    double t = FastClock::now();
    EXPECT_GT(t, 0.0);  // Should be positive (epoch relative)

    // Should be within a few seconds of program start
    // (since we use relative time, it's small)
    EXPECT_LT(t, 10.0);  // Less than 10 seconds since calibration
}

TEST(FastClockTest, NowPreciseReturnsReasonableValue) {
    double t = FastClock::now_precise();
    EXPECT_GT(t, 0.0);
    EXPECT_LT(t, 10.0);
}

TEST(FastClockTest, NowAndPreciseAreClose) {
    FastClock::calibrate();

    double t_fast = FastClock::now();
    double t_precise = FastClock::now_precise();

    double diff_ms = std::abs(t_fast - t_precise) * 1000.0;
    // Cached and precise should be within 2ms (as per plan spec)
    EXPECT_LT(diff_ms, 2.0) << "FastClock::now() deviated from precise by " << diff_ms << " ms";
}

TEST(FastClockTest, NowIsMonotonic) {
    FastClock::calibrate();

    double t0 = FastClock::now();
    double t1 = FastClock::now();
    double t2 = FastClock::now();

    EXPECT_GE(t1, t0);
    EXPECT_GE(t2, t1);
}

TEST(FastClockTest, CalibrationThreadStartsAndStops) {
    // Start calibration
    FastClock::start_calibration();

    // Give it a moment to update
    std::this_thread::sleep_for(std::chrono::milliseconds(10));

    double t0 = FastClock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    double t1 = FastClock::now();

    // After 20ms sleep, timestamp should have advanced
    EXPECT_GT(t1, t0);

    // Stop calibration
    FastClock::stop_calibration();

    // After stopping, timestamp should not advance (or advance very slowly)
    double t2 = FastClock::now();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    double t3 = FastClock::now();

    // Without calibration thread, the cached value stays the same
    // (or changes very little due to now_precise fallback)
    double diff_ms = std::abs(t3 - t2) * 1000.0;
    EXPECT_LT(diff_ms, 100.0);  // Should not have advanced much
}

TEST(FastClockTest, MultipleStartCallsAreSafe) {
    FastClock::start_calibration();
    FastClock::start_calibration();  // Should not crash or deadlock
    FastClock::start_calibration();

    double t = FastClock::now();
    EXPECT_GT(t, 0.0);

    FastClock::stop_calibration();
}

TEST(FastClockTest, MultipleStopCallsAreSafe) {
    FastClock::start_calibration();
    FastClock::stop_calibration();
    FastClock::stop_calibration();  // Should not crash
    FastClock::stop_calibration();
}

TEST(FastClockTest, NowLatencyIsLow) {
    FastClock::calibrate();

    constexpr int kSamples = 10000;
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < kSamples; ++i) {
        volatile double t = FastClock::now();
        (void)t;
    }
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    double avg_ns = total_ns / kSamples;

    // FastClock::now() should be under 50ns per call (cached atomic read)
    EXPECT_LT(avg_ns, 50.0) << "FastClock::now() avg latency = " << avg_ns << " ns";
}

}  // namespace
}  // namespace tyche
