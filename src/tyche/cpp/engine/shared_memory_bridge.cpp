#include "tyche/cpp/engine/shared_memory_bridge.h"
#include "tyche/cpp/engine/shared_memory_queue.h"
#include "tyche/cpp/engine/dynamic_library.h"
#include "tyche/cpp/engine/engine.h"
#include "tyche/cpp/message.h"

#include <algorithm>
#include <chrono>
#include <iostream>
#include <cstring>

namespace tyche {

// ── Little-endian helpers ───────────────────────────────────────────

static uint16_t read_u16_le(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

static void write_u16_le(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v);
    p[1] = static_cast<uint8_t>(v >> 8);
}

// ── Topic parsing ───────────────────────────────────────────────────

std::string SharedMemoryBridge::_parse_topic(const std::vector<uint8_t>& data,
                                              std::vector<uint8_t>& payload) {
    if (data.size() < 2) {
        payload = data;
        return "";
    }
    uint16_t topic_len = read_u16_le(data.data());
    size_t header_size = 2 + topic_len;
    if (data.size() < header_size) {
        payload = data;
        return "";
    }
    std::string topic(data.begin() + 2, data.begin() + 2 + topic_len);
    payload.assign(data.begin() + header_size, data.end());
    return topic;
}

// ── Lifecycle ───────────────────────────────────────────────────────

SharedMemoryBridge::SharedMemoryBridge() = default;

SharedMemoryBridge::~SharedMemoryBridge() {
    stop();
}

void SharedMemoryBridge::configure(std::vector<ShmModuleConfig> modules,
                                   std::vector<ShmBridgeConfig> bridges) {
    // Pre-create raw bridge queues (owner = true)
    for (auto& bc : bridges) {
        BridgeEntry entry;
        entry.queue = std::make_unique<SharedMemoryQueue>(
            SharedMemoryQueue::Config{bc.shm_queue_name, 1024, 65536}, true);
        entry.zmq_topic = bc.zmq_topic;
        if (entry.queue->is_valid()) {
            std::lock_guard lock(_bridges_lock);
            _bridges.push_back(std::move(entry));
        } else {
            std::cerr << "[SharedMemoryBridge] Failed to create queue: "
                      << bc.shm_queue_name << std::endl;
        }
    }

    // Load modules
    for (auto& mc : modules) {
        load_module(mc);
    }
}

void SharedMemoryBridge::start(TycheEngine* engine) {
    if (_running.load()) return;
    _engine = engine;
    _running.store(true, std::memory_order_release);
    _worker = std::thread(&SharedMemoryBridge::_worker_loop, this);
}

void SharedMemoryBridge::stop() {
    if (!_running.load()) return;
    _running.store(false, std::memory_order_release);

    // Call stop functions for all loaded modules
    {
        std::lock_guard lock(_modules_lock);
        for (auto& [name, mod] : _modules) {
            if (mod.stop_fn) {
                try { mod.stop_fn(); } catch (...) {}
            }
        }
    }

    if (_worker.joinable()) {
        _worker.join();
    }

    // Join all module threads
    {
        std::lock_guard lock(_modules_lock);
        for (auto& [name, mod] : _modules) {
            if (mod.run_thread.joinable()) {
                mod.run_thread.join();
            }
        }
        _modules.clear();
    }

    _engine = nullptr;
}

bool SharedMemoryBridge::is_running() const {
    return _running.load(std::memory_order_relaxed);
}

size_t SharedMemoryBridge::module_count() const {
    std::lock_guard lock(_modules_lock);
    return _modules.size();
}

size_t SharedMemoryBridge::bridge_count() const {
    std::lock_guard lock(_bridges_lock);
    return _bridges.size();
}

// ── Module loading ──────────────────────────────────────────────────

std::string SharedMemoryBridge::load_module(const ShmModuleConfig& config) {
    auto lib = std::make_unique<DynamicLibrary>(config.library_path);
    if (!lib->is_loaded()) {
        std::cerr << "[SharedMemoryBridge] Failed to load module: " << config.library_path
                  << " - " << lib->last_error() << std::endl;
        return "";
    }

    auto init_fn = lib->get_function<int(const char*)>(TYCHE_MODULE_INIT_NAME);
    auto run_fn = lib->get_function<int(void)>(TYCHE_MODULE_RUN_NAME);
    auto stop_fn = lib->get_function<void(void)>(TYCHE_MODULE_STOP_NAME);
    auto get_ifaces_fn = lib->get_function<const char*(void)>(TYCHE_MODULE_GET_INTERFACES_NAME);

    if (!init_fn || !run_fn) {
        std::cerr << "[SharedMemoryBridge] Module missing required exports: "
                  << config.library_path << std::endl;
        return "";
    }

    // Create shared memory queue (owner = true, the engine owns it)
    auto queue = std::make_unique<SharedMemoryQueue>(
        SharedMemoryQueue::Config{config.shm_queue_name, 1024, 65536}, true);

    if (!queue->is_valid()) {
        std::cerr << "[SharedMemoryBridge] Failed to create queue for module: "
                  << config.shm_queue_name << std::endl;
        return "";
    }

    // Initialize module
    if (init_fn(config.shm_queue_name.c_str()) != 0) {
        std::cerr << "[SharedMemoryBridge] Module init failed: " << config.library_path << std::endl;
        return "";
    }

    // Get interfaces if available
    std::string module_id = "shm_" + config.shm_queue_name;
    if (get_ifaces_fn) {
        const char* ifaces_json = get_ifaces_fn();
        if (ifaces_json) {
            std::cerr << "[SharedMemoryBridge] Module " << module_id
                      << " interfaces: " << ifaces_json << std::endl;
        }
    }

    // Start module in a separate thread (run() blocks)
    std::thread run_thread([run_fn, module_id]() {
        std::cerr << "[SharedMemoryBridge] Module " << module_id << " started" << std::endl;
        int rc = run_fn();
        std::cerr << "[SharedMemoryBridge] Module " << module_id
                  << " exited with code " << rc << std::endl;
    });

    // Store module
    {
        std::lock_guard lock(_modules_lock);
        LoadedModule mod;
        mod.library = std::move(lib);
        mod.queue = std::move(queue);
        mod.module_id = module_id;
        mod.topics = config.zmq_topics;
        mod.stop_fn = stop_fn;
        mod.run_thread = std::move(run_thread);
        _modules[config.shm_queue_name] = std::move(mod);
    }

    std::cerr << "[SharedMemoryBridge] Loaded module " << module_id
              << " from " << config.library_path << std::endl;

    return module_id;
}

void SharedMemoryBridge::unload_module(const std::string& shm_queue_name) {
    std::lock_guard lock(_modules_lock);
    auto it = _modules.find(shm_queue_name);
    if (it != _modules.end()) {
        if (it->second.stop_fn) {
            try { it->second.stop_fn(); } catch (...) {}
        }
        if (it->second.run_thread.joinable()) {
            it->second.run_thread.join();
        }
        _modules.erase(it);
    }
}

// ── Worker loop ─────────────────────────────────────────────────────

void SharedMemoryBridge::_worker_loop() {
    while (_running.load(std::memory_order_relaxed)) {
        bool any_activity = false;

        // Poll module queues
        {
            std::lock_guard lock(_modules_lock);
            for (auto& [name, mod] : _modules) {
                if (!mod.queue) continue;

                while (_running.load(std::memory_order_relaxed)) {
                    auto msg = mod.queue->read();
                    if (!msg.has_value()) break;

                    any_activity = true;
                    std::vector<uint8_t> payload;

                    if (!mod.topics.empty()) {
                        // Static topic mapping: ignore embedded topic, use configured topics
                        payload = std::move(msg.value());
                        for (const auto& topic : mod.topics) {
                            _forward_to_zmq(topic, payload);
                        }
                    } else {
                        // Dynamic topic: extract from message
                        std::string topic = _parse_topic(msg.value(), payload);
                        if (!topic.empty()) {
                            _forward_to_zmq(topic, payload);
                        } else {
                            std::cerr << "[SharedMemoryBridge] Module " << mod.module_id
                                      << " sent message without valid topic prefix" << std::endl;
                        }
                    }
                }
            }
        }

        // Poll raw bridge queues
        {
            std::lock_guard lock(_bridges_lock);
            for (auto& entry : _bridges) {
                if (!entry.queue) continue;

                while (_running.load(std::memory_order_relaxed)) {
                    auto msg = entry.queue->read();
                    if (!msg.has_value()) break;

                    any_activity = true;
                    std::vector<uint8_t> payload;
                    std::string topic = _parse_topic(msg.value(), payload);

                    if (!topic.empty()) {
                        _forward_to_zmq(topic, payload);
                    } else {
                        // Fallback: forward entire message as payload with configured topic
                        _forward_to_zmq(entry.zmq_topic, msg.value());
                    }
                }
            }
        }

        if (!any_activity) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
}

// ── ZMQ forwarding ──────────────────────────────────────────────────

void SharedMemoryBridge::_forward_to_zmq(const std::string& topic,
                                          const std::vector<uint8_t>& payload) {
    if (!_engine || topic.empty()) return;

    // Build a msgpack Message and inject into engine
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "shm_bridge";
    msg.event = topic;
    // Store raw payload bytes in the message
    msg.payload["raw_data"] = payload;

    auto serialized = serialize(msg);
    _engine->inject_event(topic, serialized);
}

} // namespace tyche
