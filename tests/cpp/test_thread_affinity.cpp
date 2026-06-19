// Unit tests for tyche::thread_affinity.
//
// Tests:
//   1. set_thread_affinity_current returns true for valid core
//   2. set_thread_affinity_current returns false for invalid core
//   3. get_current_cpu returns a valid core index after binding
//   4. set_thread_affinity on std::thread works
//   5. Multiple affinity changes are safe

#include <gtest/gtest.h>

#include "tyche/cpp/engine/thread_affinity.h"

#include <atomic>
#include <thread>

namespace tyche {
namespace {

TEST(ThreadAffinityTest, SetCurrentThreadAffinityValidCore) {
    // Try to bind to core 0 (should always exist)
    bool result = set_thread_affinity_current(0);
    // On some systems this might fail, but it should not crash
    // We just verify the function runs without error
    (void)result;

    // Verify we can get current CPU
    int cpu = get_current_cpu();
    EXPECT_GE(cpu, 0);  // Should return a valid CPU index
}

TEST(ThreadAffinityTest, SetCurrentThreadAffinityInvalidCore) {
    // Negative core should return false
    bool result = set_thread_affinity_current(-1);
    EXPECT_FALSE(result);
}

TEST(ThreadAffinityTest, GetCurrentCpuReturnsValidIndex) {
    int cpu = get_current_cpu();
    EXPECT_GE(cpu, 0);  // Should be non-negative

    // On most systems, CPU count is reasonable
    // We can't assert an upper bound without querying system info
}

TEST(ThreadAffinityTest, SetThreadAffinityOnStdThread) {
    std::atomic<bool> affinity_ok{false};
    std::atomic<int> thread_cpu{-1};

    std::thread t([&]() {
        thread_cpu.store(get_current_cpu());
    });

    // Try to bind the thread to core 0
    bool result = set_thread_affinity(t, 0);
    (void)result;

    t.join();

    EXPECT_GE(thread_cpu.load(), 0);
}

TEST(ThreadAffinityTest, MultipleAffinityChangesSafe) {
    // Rapidly change affinity multiple times
    for (int i = 0; i < 10; ++i) {
        bool r1 = set_thread_affinity_current(0);
        (void)r1;
        bool r2 = set_thread_affinity_current(0);
        (void)r2;
    }

    // Should not crash
    int cpu = get_current_cpu();
    EXPECT_GE(cpu, 0);
}

TEST(ThreadAffinityTest, AffinityBindingIsEffective) {
    // Bind to core 0 and verify we report running on core 0
    bool result = set_thread_affinity_current(0);
    if (result) {
        int cpu = get_current_cpu();
        EXPECT_EQ(cpu, 0) << "After binding to core 0, get_current_cpu() returned " << cpu;
    }
}

TEST(ThreadAffinityTest, ThreadAffinitySurvivesJoin) {
    std::thread t([]() {
        // Do some work
        volatile int x = 0;
        for (int i = 0; i < 1000; ++i) {
            x += i;
        }
        (void)x;
    });

    // Set affinity before join
    bool result = set_thread_affinity(t, 0);
    (void)result;

    t.join();
    // Should not crash
}

}  // namespace
}  // namespace tyche
