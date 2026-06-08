#pragma once

// TycheEngine - Central event/job routing engine (C++ rewrite).
//
// Mirrors Python src/tyche/engine.py. Uses 10 worker threads for:
//   registration, registration_egress, heartbeat, heartbeat_receive,
//   monitor, event_proxy, event_egress, admin, job_router, job_timeout.

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <queue>
#include <shared_mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "tyche/cpp/types.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/string_intern.h"
#include "tyche/cpp/engine/topic_queue.h"
#include "tyche/cpp/engine/sharded_topic_map.h"
#include "tyche/cpp/engine/heartbeat_manager.h"
#include "tyche/cpp/engine/dead_letter_store.h"

namespace tyche {

// Forward declaration to avoid circular include
class SharedMemoryBridge;

/// Job timeout tracking information
struct JobTrackingInfo {
    std::vector<uint8_t> requester_id;   // ZMQ identity of requester
    std::string handler_id;              // assigned handler module_id; empty = waiting
    std::string topic;
    double dispatch_time = 0.0;
    double wait_start_time = 0.0;
    float wait_timeout = 30.0f;
    float run_timeout = 60.0f;
    std::vector<uint8_t> topic_frame;    // raw topic bytes for forwarding
    std::vector<uint8_t> message_frame;  // raw message bytes for forwarding/retry
};

class TycheEngine {
public:
    TycheEngine(
        Endpoint registration_endpoint,
        Endpoint event_endpoint,
        Endpoint heartbeat_endpoint,
        Endpoint heartbeat_recv_endpoint = {"127.0.0.1", 5560},
        Endpoint admin_endpoint = {"127.0.0.1", 5558},
        Endpoint job_endpoint = {"127.0.0.1", 5564},
        int queue_capacity = 10000,
        std::string data_dir = "data");

    ~TycheEngine();

    TycheEngine(const TycheEngine&) = delete;
    TycheEngine& operator=(const TycheEngine&) = delete;

    /// Block until stop() is called
    void run();

    /// Start all workers, return immediately
    void start_nonblocking();

    /// Graceful shutdown
    void stop();

    /// Register a module (thread-safe)
    void register_module(const ModuleInfo& info);

    /// Unregister a module (thread-safe)
    void unregister_module(const std::string& module_id);

    /// Inject an event directly into the engine's topic queues.
    /// Used by the SharedMemoryBridge to forward messages from DLL/SO modules.
    void inject_event(const std::string& topic, const std::vector<uint8_t>& message_data);

    /// Access the shared memory bridge (for configuration after construction).
    SharedMemoryBridge* shm_bridge() const { return _shm_bridge.get(); }

    bool is_running() const noexcept { return _running.load(std::memory_order_relaxed); }

private:
    // ── Configuration ──
    Endpoint _registration_endpoint;
    Endpoint _event_endpoint;
    Endpoint _event_sub_endpoint;   // XSUB = event_endpoint.port + 1
    Endpoint _heartbeat_endpoint;
    Endpoint _heartbeat_recv_endpoint;
    Endpoint _admin_endpoint;
    Endpoint _job_endpoint;
    int _queue_capacity;
    double _broadcast_ttl = 60.0;
    double _topic_queue_ttl = 60.0;

    // ── Running state ──
    std::atomic<bool> _running{false};

    // ── Counters ──
    std::atomic<uint64_t> _event_count{0};
    std::atomic<uint64_t> _register_count{0};
    double _start_time = 0.0;

    // ── ZMQ context (opaque PIMPL — keeps zmq.hpp out of this header) ──
    struct ZmqContext;
    std::unique_ptr<ZmqContext> _zmq_ctx;

    // ── String interning (OPT-3) ──
    // Maps topic strings and module IDs to dense uint32_t IDs at registration
    // time. Eliminates repeated hashing and string comparisons on hot paths.
    StringIntern _intern;

    // ── Module management (shared_mutex for concurrent reads) ──
    mutable std::shared_mutex _modules_lock;
    std::unordered_map<std::string, ModuleInfo> _modules;
    std::unordered_map<InternId, std::vector<std::string>> _topic_subscribers;
    std::unordered_map<InternId, std::vector<std::string>> _topic_producers;
    std::unordered_map<InternId, std::vector<std::string>> _job_handlers;
    std::unordered_map<std::string, std::unordered_map<std::string, bool>> _module_availability;
    std::unordered_map<std::string, std::unordered_set<std::string>> _unavailable_handlers;

    // ── Topic queue system (OPT-2: sharded lock-free lookup) ──
    // Replaces global std::mutex + unordered_map with per-bucket spinlocks.
    // Event proxy (single writer) and egress/monitor/registration threads
    // contend only when hashing to the same bucket.
    ShardedTopicQueueMap _topic_queues;

    // ── Egress wakeup ──
    std::mutex _egress_wakeup_lock;
    std::condition_variable _egress_wakeup_cv;
    bool _egress_wakeup_flag = false;

    // ── Registration inter-thread queues ──
    struct RegRequest {
        std::vector<uint8_t> identity;
        std::vector<uint8_t> msg_data;
    };
    std::queue<RegRequest> _reg_in_queue;
    std::mutex _reg_in_lock;
    std::condition_variable _reg_in_cv;

    struct MultipartMsg {
        std::vector<std::vector<uint8_t>> frames;
    };
    std::queue<MultipartMsg> _reg_out_queue;
    std::mutex _reg_out_lock;

    // ── Job routing state ──
    mutable std::mutex _job_lock;
    std::unordered_map<std::string, std::vector<uint8_t>> _pending_jobs;
    std::unordered_map<std::string, JobTrackingInfo> _job_tracking;
    std::unordered_map<InternId, size_t> _job_round_robin;

    // ── Job inter-thread queues ──
    struct JobTimeoutEvent {
        std::string correlation_id;
        std::string reason;
    };
    std::queue<JobTimeoutEvent> _job_timeout_events;
    std::mutex _job_timeout_events_lock;

    struct RecoveryEvent {
        std::string module_id;
        std::vector<std::string> recovered_topics;
    };
    std::queue<RecoveryEvent> _recovery_events;
    std::mutex _recovery_events_lock;

    // ── Subsystems ──
    HeartbeatManager _heartbeat_manager;
    DeadLetterStore _dead_letter_store;

    // ── Shared memory bridge ──
    std::unique_ptr<SharedMemoryBridge> _shm_bridge;

    // ── Worker threads ──
    std::vector<std::thread> _threads;

    // ── 10 worker thread functions ──
    void _registration_worker();
    void _registration_egress_worker();
    void _heartbeat_worker();
    void _heartbeat_receive_worker();
    void _monitor_worker();
    void _event_proxy_worker();
    void _event_egress_worker();
    void _admin_worker();
    void _job_router_worker();
    void _job_timeout_worker();

    // ── Helper methods ──
    void _enqueue_from_xsub(const std::vector<std::vector<uint8_t>>& frames);
    std::string _create_module_id(const std::string& family_name);
    bool _is_handler_available(const std::string& module_id, const std::string& topic) const;
    static double _now();
};

}  // namespace tyche
