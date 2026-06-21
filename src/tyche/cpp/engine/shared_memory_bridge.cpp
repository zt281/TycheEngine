#include "tyche/cpp/engine/shared_memory_bridge.h"
#include "tyche/cpp/engine/shared_memory_queue.h"
#include "tyche/cpp/engine/dynamic_library.h"
#include "tyche/cpp/engine/engine.h"
#include "tyche/cpp/engine/adaptive_spin.h"
#include "tyche/cpp/engine/module_interface.h"
#include "tyche/cpp/message.h"

#include <algorithm>
#include <chrono>
#include <future>
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

// ── Topic parsing (new zero-allocation version) ─────────────────────

bool SharedMemoryBridge::_parse_topic(const uint8_t* data, size_t data_size,
                                       std::string& out_topic, size_t& out_payload_offset) {
    if (data_size < 2) return false;
    uint16_t topic_len = read_u16_le(data);
    if (2 + topic_len > data_size) return false;
    out_topic.assign(reinterpret_cast<const char*>(data + 2), topic_len);
    out_payload_offset = 2 + topic_len;
    return true;
}

// ── Topic parsing (legacy vector version) ───────────────────────────

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

    // Rebuild snapshot if already running
    if (_running.load(std::memory_order_relaxed)) {
        _rebuild_snapshot();
    }
}

void SharedMemoryBridge::start(TycheEngine* engine) {
    if (_running.load()) return;
    _engine = engine;

    // P0: Clean up stale SHM segments from crashed processes
    SharedMemoryQueue::cleanup_stale();

    _running.store(true, std::memory_order_release);

    // Build initial snapshot
    _rebuild_snapshot();

    _worker = std::thread(&SharedMemoryBridge::_worker_loop, this);
}

void SharedMemoryBridge::stop() {
    if (!_running.exchange(false)) return;

    // Stop worker thread first
    if (_worker.joinable()) {
        _worker.join();
    }

    // Stop all modules with timeout
    {
        std::lock_guard lock(_modules_lock);
        for (auto& [name, mod] : _modules) {
            if (mod.stop_fn) {
                try { mod.stop_fn(); } catch (...) {}
            }
            if (mod.run_thread.joinable()) {
                auto future = std::async(std::launch::async, [&mod]() {
                    mod.run_thread.join();
                });
                if (future.wait_for(std::chrono::seconds(MODULE_STOP_TIMEOUT_SEC)) == std::future_status::timeout) {
                    mod.run_thread.detach();
                    std::cerr << "[SharedMemoryBridge] Warning: module '" << name
                              << "' failed to stop within timeout, thread detached" << std::endl;
                }
            }
        }
        _modules.clear();
    }

    // Clear snapshot
    {
        std::lock_guard<std::mutex> slk(_snapshot_lock);
        _snapshot.reset();
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

    // P0: Optional ABI version verification
    auto version_fn = lib->get_function<const char*()>(TYCHE_MODULE_VERSION_NAME);
    if (version_fn) {
        const char* mod_version = version_fn();
        if (mod_version && std::string(mod_version) != TYCHE_MODULE_ABI_VERSION) {
            std::cerr << "[SharedMemoryBridge] Module ABI version mismatch: "
                      << "expected " << TYCHE_MODULE_ABI_VERSION
                      << ", got " << mod_version << std::endl;
            return "";  // reject incompatible module
        }
    } else {
        std::cerr << "[SharedMemoryBridge] Warning: module does not export "
                  << TYCHE_MODULE_VERSION_NAME << ", skipping version check" << std::endl;
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

    // Rebuild snapshot so worker loop picks up the new module
    if (_running.load(std::memory_order_relaxed)) {
        _rebuild_snapshot();
    }

    std::cerr << "[SharedMemoryBridge] Loaded module " << module_id
              << " from " << config.library_path << std::endl;

    return module_id;
}

void SharedMemoryBridge::unload_module(const std::string& shm_queue_name) {
    std::unique_lock<std::mutex> lk(_modules_lock);
    auto it = _modules.find(shm_queue_name);
    if (it == _modules.end()) return;

    // Move out to release lock before blocking operations
    LoadedModule mod = std::move(it->second);
    _modules.erase(it);
    lk.unlock();

    // Rebuild snapshot immediately (removes module from worker loop)
    _rebuild_snapshot();

    // Signal stop
    if (mod.stop_fn) {
        try { mod.stop_fn(); } catch (...) {}
    }

    // Timed join — prevent infinite blocking from unresponsive modules
    if (mod.run_thread.joinable()) {
        auto future = std::async(std::launch::async, [&mod]() {
            mod.run_thread.join();
        });
        if (future.wait_for(std::chrono::seconds(MODULE_STOP_TIMEOUT_SEC)) == std::future_status::timeout) {
            mod.run_thread.detach();
            std::cerr << "[SharedMemoryBridge] Warning: module '" << shm_queue_name
                      << "' failed to stop within " << MODULE_STOP_TIMEOUT_SEC
                      << "s timeout, thread detached" << std::endl;
        }
    }
    // mod goes out of scope — library unloaded via RAII
}

// ── Snapshot management ─────────────────────────────────────────────

void SharedMemoryBridge::_rebuild_snapshot() {
    auto snap = std::make_shared<BridgeSnapshot>();

    // Build module entries (under _modules_lock)
    {
        std::lock_guard<std::mutex> lk(_modules_lock);
        for (const auto& [name, mod] : _modules) {
            if (mod.queue) {
                snap->modules.push_back({mod.queue.get(), mod.topics});
            }
        }
    }

    // Build bridge entries (under _bridges_lock)
    {
        std::lock_guard<std::mutex> lk(_bridges_lock);
        for (const auto& entry : _bridges) {
            if (entry.queue) {
                snap->bridges.push_back({entry.queue.get(), entry.zmq_topic});
            }
        }
    }

    // Atomically publish new snapshot
    {
        std::lock_guard<std::mutex> lk(_snapshot_lock);
        _snapshot = std::move(snap);
    }
}

// ── Worker loop (P0: zero-allocation + adaptive spin) ───────────────

void SharedMemoryBridge::_worker_loop() {
    // Pre-allocate TLS buffer for zero-allocation reads
    thread_local std::vector<uint8_t> tls_buffer(65536);

    while (_running.load(std::memory_order_relaxed)) {
        bool any_activity = false;

        // Load snapshot atomically (lock-free read path)
        std::shared_ptr<BridgeSnapshot> snap;
        {
            std::lock_guard<std::mutex> lk(_snapshot_lock);
            snap = _snapshot;
        }

        if (snap) {
            // Poll module queues (no mutex held during reads!)
            for (const auto& entry : snap->modules) {
                if (!entry.queue) continue;
                size_t msg_size = 0;
                while (_running.load(std::memory_order_relaxed) &&
                       entry.queue->read_into(tls_buffer.data(), tls_buffer.size(), msg_size)) {
                    any_activity = true;

                    if (!entry.topics.empty()) {
                        // Static topic mapping: forward to all configured topics
                        for (const auto& topic : entry.topics) {
                            _forward_to_zmq(topic, tls_buffer.data(), msg_size);
                        }
                    } else {
                        // Dynamic: parse topic from message
                        std::string topic;
                        size_t payload_offset = 0;
                        if (_parse_topic(tls_buffer.data(), msg_size, topic, payload_offset)) {
                            _forward_to_zmq(topic, tls_buffer.data() + payload_offset, msg_size - payload_offset);
                        }
                    }
                }
            }

            // Poll bridge queues
            for (const auto& bridge_ref : snap->bridges) {
                if (!bridge_ref.queue) continue;
                size_t msg_size = 0;
                while (_running.load(std::memory_order_relaxed) &&
                       bridge_ref.queue->read_into(tls_buffer.data(), tls_buffer.size(), msg_size)) {
                    any_activity = true;

                    // Try to parse topic from message; fallback to configured topic
                    std::string topic;
                    size_t payload_offset = 0;
                    if (_parse_topic(tls_buffer.data(), msg_size, topic, payload_offset)) {
                        _forward_to_zmq(topic, tls_buffer.data() + payload_offset, msg_size - payload_offset);
                    } else {
                        // Fallback: forward entire message as payload with configured topic
                        _forward_to_zmq(bridge_ref.zmq_topic, tls_buffer.data(), msg_size);
                    }
                }
            }
        }

        // Adaptive spin instead of fixed 1ms sleep
        if (any_activity) {
            _spinner.reset();
        } else {
            _spinner.wait();
        }
    }
}

// ── ZMQ forwarding ──────────────────────────────────────────────────

void SharedMemoryBridge::_forward_to_zmq(const std::string& topic,
                                          const uint8_t* data, size_t size) {
    if (!_engine || topic.empty()) return;
    _engine->inject_event_raw(topic, data, size);
}

void SharedMemoryBridge::_forward_to_zmq(const std::string& topic,
                                          const std::vector<uint8_t>& payload) {
    _forward_to_zmq(topic, payload.data(), payload.size());
}

} // namespace tyche
