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

#include <atomic>
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

    TycheModule(
        Endpoint engine_endpoint,
        std::string module_id,
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

    const std::string& module_id() const noexcept { return _module_id; }
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
    std::string _module_id;
    Endpoint _engine_endpoint;
    std::optional<Endpoint> _heartbeat_receive_endpoint;

    // Handler registry (event_type -> {handler, pattern}).
    mutable std::mutex _handlers_lock;
    std::unordered_map<std::string,
                       std::pair<Handler, InterfacePattern>> _handlers;

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
};

}  // namespace tyche
