#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "tyche/cpp/types.h"
#include "tyche/cpp/engine/module_interface.h"

namespace tyche {

class SharedMemoryQueue;
class DynamicLibrary;
class TycheEngine;

// Configuration for a DLL/SO module loaded via shared memory.
struct ShmModuleConfig {
    std::string library_path;       // path to .dll or .so file
    std::string shm_queue_name;     // shared memory queue name
    std::vector<std::string> zmq_topics;  // topics to forward to (optional, for static mapping)
};

// Configuration for a raw shared-memory -> ZMQ bridge (no DLL loading).
struct ShmBridgeConfig {
    std::string shm_queue_name;     // shared memory queue name
    std::string zmq_topic;          // ZMQ topic to forward to
};

// Bridges shared memory queues to the engine's ZMQ event system.
//
// Two modes of operation:
//   1. Module mode: loads a DLL/SO, creates its queue, starts it in a thread,
//      and forwards messages from the module's queue to ZMQ topics.
//   2. Raw bridge mode: creates a queue and forwards all messages to a
//      fixed ZMQ topic (useful for external processes that write to the queue).
//
// Message format on the shared-memory queue:
//   [uint16_t topic_len (LE)] [char topic[topic_len]] [uint8_t payload[]]
//
// If a module config has zmq_topics set, the topic from the message is ignored
// and all messages are forwarded to the configured topics (static mapping).
// If zmq_topics is empty, the topic is extracted from each message (dynamic).

class SharedMemoryBridge {
public:
    SharedMemoryBridge();
    ~SharedMemoryBridge();

    SharedMemoryBridge(const SharedMemoryBridge&) = delete;
    SharedMemoryBridge& operator=(const SharedMemoryBridge&) = delete;

    // Configure bridges. Must be called before start().
    void configure(std::vector<ShmModuleConfig> modules,
                   std::vector<ShmBridgeConfig> bridges);

    // Start the bridge worker thread.
    void start(TycheEngine* engine);

    // Stop the bridge worker thread and unload all modules.
    void stop();

    bool is_running() const;

    // Load and initialize a single DLL/SO module.
    // Returns module_id on success, empty string on failure.
    std::string load_module(const ShmModuleConfig& config);

    // Unload a module by its queue name.
    void unload_module(const std::string& shm_queue_name);

    size_t module_count() const;
    size_t bridge_count() const;

private:
    struct LoadedModule {
        std::unique_ptr<DynamicLibrary> library;
        std::unique_ptr<SharedMemoryQueue> queue;
        std::string module_id;
        std::vector<std::string> topics;  // static topic mapping (empty = dynamic)
        tyche_module_stop_fn stop_fn = nullptr;
        std::thread run_thread;
    };

    struct BridgeEntry {
        std::unique_ptr<SharedMemoryQueue> queue;
        std::string zmq_topic;
    };

    std::atomic<bool> _running{false};
    std::thread _worker;

    mutable std::mutex _modules_lock;
    std::unordered_map<std::string, LoadedModule> _modules;  // key = shm_queue_name

    mutable std::mutex _bridges_lock;
    std::vector<BridgeEntry> _bridges;

    TycheEngine* _engine = nullptr;

    void _worker_loop();
    void _forward_to_zmq(const std::string& topic, const std::vector<uint8_t>& payload);

    // Parse topic from message data. Returns "" if dynamic parsing fails.
    static std::string _parse_topic(const std::vector<uint8_t>& data,
                                    std::vector<uint8_t>& payload);
};

} // namespace tyche
