#pragma once

// TycheModule -- base implementation for Tyche Engine modules.
//
// Mirrors src/tyche/module.py.
//
// Connects to TycheEngine, registers interfaces, subscribes to events,
// and dispatches incoming messages to handler callbacks.
//
// Socket architecture (managed in module.cpp via PIMPL):
//   - REQ:    one-shot registration handshake (closed after use)
//   - PUB:    publish events to engine's XSUB
//   - SUB:    subscribe to events from engine's XPUB
//   - DEALER: send heartbeats to engine
//   - DEALER: job request/response (addressable via module_id)

#include <atomic>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "tyche/cpp/types.h"

namespace tyche {

class TycheModule {
public:
    using Handler = std::function<void(const Payload&)>;
    using JobHandler = std::function<Payload(const Payload&)>;

    TycheModule(
        Endpoint engine_endpoint,
        std::string family_name,
        std::optional<Endpoint> heartbeat_receive_endpoint = std::nullopt);

    virtual ~TycheModule();

    TycheModule(const TycheModule&) = delete;
    TycheModule& operator=(const TycheModule&) = delete;
    TycheModule(TycheModule&&) = delete;
    TycheModule& operator=(TycheModule&&) = delete;

    // ── Lifecycle ───────────────────────────────────────────────────

    // Start the module - returns once worker threads are up.
    virtual void start();

    // Start the module - blocks until stop() is called.
    virtual void run();

    // Stop the module gracefully.
    virtual void stop();

    // ── Accessors ───────────────────────────────────────────────────

    // Return the family name (module type identifier).
    const std::string& family_name() const noexcept { return _family_name; }

    // Return the module ID.  Before registration completes the engine-assigned
    // ID is not yet available, so we fall back to family_name.
    const std::string& module_id() const noexcept {
        return _module_id.empty() ? _family_name : _module_id;
    }

    const std::vector<Interface>& interfaces() const noexcept { return _interfaces; }
    const Endpoint& engine_endpoint() const noexcept { return _engine_endpoint; }

    bool is_running() const noexcept { return _running.load(std::memory_order_relaxed); }
    bool is_registered() const noexcept { return _registered.load(std::memory_order_relaxed); }

    // ── Event Publishing ────────────────────────────────────────────

    // Publish an event through the engine's event proxy.
    //
    // Thread-safe; serializes the message and publishes via the PUB socket.
    void send_event(
        const std::string& event,
        const Payload& payload,
        std::optional<std::string> recipient = std::nullopt);

    // ── Job Request/Response ────────────────────────────────────────

    // Send a job request and block until a response is received.
    //
    // Returns the response payload. Throws std::runtime_error on timeout
    // or if the job socket is not connected.
    Payload request_event(
        const std::string& event,
        const Payload& payload,
        float timeout = 5.0f);

protected:
    // Hook for subclasses to extend startup. Subclasses MUST call
    // TycheModule::_start_workers() in their override before performing
    // their own startup work (mirrors super()._start_workers() in Python).
    virtual void _start_workers();

    // Register a consumer handler programmatically.
    //
    // Python's TycheModule auto-discovers `on_*` methods via reflection.
    // C++ has no runtime reflection -- subclasses register their handlers
    // explicitly in their constructor.
    void _register_handler(
        const std::string& name,
        Handler handler,
        InterfacePattern pattern = InterfacePattern::ON,
        DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH);

    // Register a job handler (handle_* pattern) programmatically.
    //
    // Job handlers receive a request payload and return a response payload.
    // They are dispatched via the engine's ROUTER/DEALER job socket.
    void _register_job_handler(
        const std::string& name,
        JobHandler handler,
        DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH);

    // Register a producer declaration programmatically.
    //
    // Producer declarations are recorded in _interfaces but do NOT
    // create an inbound handler.
    void _register_producer(
        const std::string& name,
        InterfacePattern pattern = InterfacePattern::SEND,
        DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH);

    // ── State accessible to subclasses ─────────────────────────────

    // Lifecycle flags. Atomic so worker threads can read them without
    // additional synchronization.
    std::atomic<bool> _running{false};
    std::atomic<bool> _registered{false};

    // Discovered interfaces (populated by _register_handler / _register_producer).
    std::vector<Interface> _interfaces;

private:
    // Identity / configuration.
    std::string _family_name;
    std::string _module_id;  // assigned by engine on registration; empty until then
    Endpoint _engine_endpoint;
    std::optional<Endpoint> _heartbeat_receive_endpoint;

    // Handler registry (event_type -> {handler, pattern}).
    mutable std::mutex _handlers_lock;
    std::unordered_map<std::string,
                       std::pair<Handler, InterfacePattern>> _handlers;

    // Job handler registry (event_type -> job_handler).
    std::unordered_map<std::string, JobHandler> _job_handlers;

    // Pending job requests: correlation_id -> {payload, ready flag}.
    struct PendingRequest {
        Payload result;
        bool ready = false;
        std::condition_variable cv;
    };
    mutable std::mutex _pending_lock;
    std::unordered_map<std::string,
                       std::shared_ptr<PendingRequest>> _pending_requests;

    // PIMPL: ZMQ context, sockets, and worker threads live in module.cpp,
    // so this header doesn't pull in cppzmq / msgpack-cxx.
    struct Impl;
    std::unique_ptr<Impl> _impl;

    // Implementation helpers (defined in module.cpp).
    bool _register_with_engine();
    void _subscribe_to_interfaces();
    void _event_receiver_loop();
    void _heartbeat_loop();
    void _dispatch(const std::string& topic, const Payload& payload);

    // Job socket helpers.
    void _connect_job_socket();
    void _job_receiver_loop();
    void _handle_job_request(const std::string& event,
                             const Payload& payload,
                             const std::optional<std::string>& correlation_id);
    void _handle_job_response(const Payload& payload,
                              const std::optional<std::string>& correlation_id);
    static std::string _generate_correlation_id();
};

}  // namespace tyche
