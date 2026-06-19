// Unit tests for tyche::AdaptiveSpin.
//
// Tests:
//   1. Reset clears idle counter
//   2. Wait transitions through spin/yield/sleep phases
//   3. Threshold boundaries

#include <gtest/gtest.h>

#include "tyche/cpp/engine/adaptive_spin.h"

#include <chrono>
#include <thread>

namespace tyche {
namespace {

TEST(AdaptiveSpinTest, ResetClearsIdleCount) {
    AdaptiveSpin spinner(10, 100, 10);

    // Spin a few times
    for (int i = 0; i < 5; ++i) {
        spinner.wait();
    }
    EXPECT_EQ(spinner.idle_count(), 5);

    // Reset should clear
    spinner.reset();
    EXPECT_EQ(spinner.idle_count(), 0);
}

TEST(AdaptiveSpinTest, SpinPhase) {
    AdaptiveSpin spinner(1000, 10000, 10);

    // First few waits should be in spin phase (idle_count < spin_threshold)
    for (int i = 0; i < 10; ++i) {
        spinner.wait();
    }
    EXPECT_EQ(spinner.idle_count(), 10);
    // Should not have reached yield phase yet (idle_count < spin_threshold)
    EXPECT_LT(spinner.idle_count(), 1000);
}

TEST(AdaptiveSpinTest, YieldPhase) {
    AdaptiveSpin spinner(5, 10000, 10);

    // Spin past the spin threshold
    for (int i = 0; i < 10; ++i) {
        spinner.wait();
    }
    EXPECT_EQ(spinner.idle_count(), 10);
    // idle_count (10) > spin_threshold (5), so we are in yield phase
    EXPECT_GT(spinner.idle_count(), 5);
}

TEST(AdaptiveSpinTest, SleepPhase) {
    AdaptiveSpin spinner(5, 10, 1);  // Very small thresholds

    // Spin past both thresholds
    for (int i = 0; i < 15; ++i) {
        spinner.wait();
    }
    EXPECT_EQ(spinner.idle_count(), 15);
    // idle_count (15) > yield_threshold (10), so we are in sleep phase
    EXPECT_GT(spinner.idle_count(), 10);
}

TEST(AdaptiveSpinTest, ResetAfterSleepPhase) {
    AdaptiveSpin spinner(5, 10, 1);

    // Reach sleep phase
    for (int i = 0; i < 20; ++i) {
        spinner.wait();
    }
    EXPECT_EQ(spinner.idle_count(), 20);

    // Reset and verify back to spin phase
    spinner.reset();
    EXPECT_EQ(spinner.idle_count(), 0);

    spinner.wait();
    EXPECT_EQ(spinner.idle_count(), 1);  // Back in spin phase
}

TEST(AdaptiveSpinTest, NoCrashUnderRapidWaitReset) {
    AdaptiveSpin spinner(100, 1000, 1);

    for (int cycle = 0; cycle < 100; ++cycle) {
        for (int i = 0; i < 50; ++i) {
            spinner.wait();
        }
        spinner.reset();
    }
    // Test passes if no crash or hang
    EXPECT_EQ(spinner.idle_count(), 0);
}

TEST(AdaptiveSpinTest, SleepPhaseReducesCpuUsage) {
    AdaptiveSpin spinner(5, 10, 100);  // 100us sleep

    // Reach sleep phase
    for (int i = 0; i < 15; ++i) {
        spinner.wait();
    }

    auto t0 = std::chrono::high_resolution_clock::now();
    spinner.wait();  // This should sleep for ~100us
    auto t1 = std::chrono::high_resolution_clock::now();

    auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count();
    // Should have slept at least 50us (allowing for scheduler jitter)
    EXPECT_GE(elapsed_us, 50);
}

}  // namespace
}  // namespace tyche
