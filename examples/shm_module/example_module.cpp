// Example Tyche shared-memory module.
// Build as DLL (Windows) or SO (Linux) and load via engine config.
//
// Build (Windows):
//   cl /LD example_module.cpp /Feexample_module.dll
//
// Build (Linux):
//   g++ -shared -fPIC example_module.cpp -o example_module.so

#include "tyche/cpp/engine/module_interface.h"
#include "tyche/cpp/engine/shared_memory_queue.h"

#include <chrono>
#include <cstring>
#include <math>
#include <thread>
#include <vector>

static tyche::SharedMemoryQueue* g_queue = nullptr;
static bool g_running = false;

// Little-endian write
static void write_u16_le(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v);
    p[1] = static_cast<uint8_t>(v >> 8);
}

extern "C" {

int tyche_module_init(const char* shm_queue_name) {
    g_queue = new tyche::SharedMemoryQueue(
        tyche::SharedMemoryQueue::Config{shm_queue_name, 1024, 65536}, false);
    if (!g_queue->is_valid()) {
        delete g_queue;
        g_queue = nullptr;
        return -1;
    }
    g_running = true;
    return 0;
}

int tyche_module_run() {
    if (!g_queue) return -1;

    int counter = 0;
    while (g_running) {
        // Build a message with topic prefix
        std::string topic = "tick";
        std::string payload = "{\"symbol\": \"AAPL\", \"price\": 150.0, \"seq\": " + std::to_string(counter) + "}";

        size_t total_size = 2 + topic.size() + payload.size();
        std::vector<uint8_t> msg(total_size);
        write_u16_le(msg.data(), static_cast<uint16_t>(topic.size()));
        std::memcpy(msg.data() + 2, topic.data(), topic.size());
        std::memcpy(msg.data() + 2 + topic.size(), payload.data(), payload.size());

        // Write to shared memory queue (retry if full)
        while (!g_queue->write(msg) && g_running) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }

        ++counter;
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    return 0;
}

void tyche_module_stop() {
    g_running = false;
}

const char* tyche_module_get_interfaces() {
    return "[{\"name\":\"on_tick\",\"pattern\":\"on\",\"event_type\":\"tick\"}]";
}

} // extern "C"
