// Stub shared library for testing SharedMemoryBridge module loading.
// This library implements the Tyche module interface and can be loaded
// by SharedMemoryBridge::load_module() for testing purposes.

#include <cstring>
#include <iostream>

#include "tyche/cpp/engine/module_interface.h"

static char g_queue_name[256] = {0};
static bool g_running = false;

extern "C" {

int tyche_module_init(const char* shm_queue_name) {
    std::strncpy(g_queue_name, shm_queue_name, sizeof(g_queue_name) - 1);
    g_queue_name[sizeof(g_queue_name) - 1] = '\0';
    std::cerr << "[StubModule] init with queue: " << g_queue_name << std::endl;
    return 0;
}

int tyche_module_run(void) {
    std::cerr << "[StubModule] run started" << std::endl;
    // Return immediately for testing - don't block
    std::cerr << "[StubModule] run exiting" << std::endl;
    return 0;
}

void tyche_module_stop(void) {
    g_running = false;
    std::cerr << "[StubModule] stop called" << std::endl;
}

const char* tyche_module_get_interfaces(void) {
    return R"([{"name":"on_test","pattern":"on","event_type":"test"}])";
}

} // extern "C"
