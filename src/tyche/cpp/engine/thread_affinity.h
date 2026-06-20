#pragma once

// thread_affinity.h -- CPU affinity binding for low-latency threads.
//
// Platform support:
//   - Windows: SetThreadAffinityMask() / GetCurrentProcessorNumber()
//   - Linux:   pthread_setaffinity_np() / sched_getcpu()

#include <thread>
#include <cstdint>

namespace tyche {

// Set thread affinity to a specific CPU core. Returns false on failure.
bool set_thread_affinity(std::thread& t, int cpu_core);

// Set affinity for current thread.
bool set_thread_affinity_current(int cpu_core);

// Get current CPU core index. Returns -1 on failure.
int get_current_cpu() noexcept;

} // namespace tyche
