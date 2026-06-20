// thread_affinity.cpp -- CPU affinity implementation.

#include "tyche/cpp/engine/thread_affinity.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#include <sched.h>
#endif

namespace tyche {

bool set_thread_affinity(std::thread& t, int cpu_core) {
    if (cpu_core < 0) return false;

#if defined(_WIN32)
    DWORD_PTR mask = 1ULL << static_cast<DWORD_PTR>(cpu_core);
    HANDLE handle = t.native_handle();
    DWORD_PTR result = SetThreadAffinityMask(handle, mask);
    return result != 0;
#else
    pthread_t handle = t.native_handle();
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(static_cast<size_t>(cpu_core), &cpuset);
    int rc = pthread_setaffinity_np(handle, sizeof(cpuset), &cpuset);
    return rc == 0;
#endif
}

bool set_thread_affinity_current(int cpu_core) {
    if (cpu_core < 0) return false;

#if defined(_WIN32)
    DWORD_PTR mask = 1ULL << static_cast<DWORD_PTR>(cpu_core);
    DWORD_PTR result = SetThreadAffinityMask(GetCurrentThread(), mask);
    return result != 0;
#else
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(static_cast<size_t>(cpu_core), &cpuset);
    int rc = sched_setaffinity(0, sizeof(cpuset), &cpuset);
    return rc == 0;
#endif
}

int get_current_cpu() noexcept {
#if defined(_WIN32)
    return static_cast<int>(GetCurrentProcessorNumber());
#else
    return sched_getcpu();
#endif
}

} // namespace tyche
