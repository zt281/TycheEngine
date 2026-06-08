// Full ZMQ-based implementation of tyche::TycheModule.
//
// Mirrors the logic in src/tyche/module.py:
//   - REGISTER over a one-shot REQ socket; capture engine_pub/sub_port
//   - PUB socket  -> engine XSUB (event publishing)
//   - SUB socket  <- engine XPUB (event reception, dispatch loop)
//   - DEALER socket for heartbeats
//   - DEALER socket for job request/response (addressable via module_id)

#include "tyche/cpp/module.h"
#include "tyche/cpp/message.h"

#include <zmq.hpp>
#include <zmq_addon.hpp>
#include <msgpack.hpp>

#include <chrono>
#include <iostream>
#include <mutex>
#include <random>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace tyche {

// ── PIMPL: ZMQ state ──────────────────────────────────────────────────

struct TycheModule::Impl {
    zmq::context_t context{1};
    std::unique_ptr<zmq::socket_t> pub_socket;
    std::unique_ptr<zmq::socket_t> sub_socket;
    std::unique_ptr<zmq::socket_t> heartbeat_socket;
    std::unique_ptr<zmq::socket_t> job_socket;

    std::thread event_receiver_thread;
    std::thread heartbeat_thread;
    std::thread job_receiver_thread;

    int engine_pub_port = 0;  // engine XPUB port (we SUB here)
    int engine_sub_port = 0;  // engine XSUB port (we PUB here)
    int engine_job_port = 0;  // engine ROUTER port (job routing)

    std::mutex pub_lock;  // thread-safe PUB sends
    std::mutex job_lock;  // thread-safe job socket sends
};

// ── Construction / destruction ─────────────────────────────────────

TycheModule::TycheModule(
    Endpoint engine_endpoint,
    std::string family_name,
    std::optional<Endpoint> heartbeat_receive_endpoint)
    : _family_name(std::move(family_name)),
      _engine_endpoint(std::move(engine_endpoint)),
      _heartbeat_receive_endpoint(std::move(heartbeat_receive_endpoint)),
      _impl(std::make_unique<Impl>()) {}

// Out-of-line so that ~unique_ptr<Impl> sees the complete Impl type.
TycheModule::~TycheModule() {
    if (_running.load()) {
        stop();
    }
}

// ── Lifecycle ──────────────────────────────────────────────────────

void TycheModule::start() {
    _start_workers();
}

void TycheModule::run() {
    start();
    while (_running.load(std::memory_order_relaxed)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

void TycheModule::stop() {
    _running.store(false, std::memory_order_relaxed);

    // Wait for worker threads to finish
    if (_impl->event_receiver_thread.joinable()) {
        _impl->event_receiver_thread.join();
    }
    if (_impl->heartbeat_thread.joinable()) {
        _impl->heartbeat_thread.join();
    }
    if (_impl->job_receiver_thread.joinable()) {
        _impl->job_receiver_thread.join();
    }

    // Wake up any pending request waiters
    {
        std::lock_guard<std::mutex> lock(_pending_lock);
        for (auto& [id, req] : _pending_requests) {
            req->ready = true;
            req->cv.notify_all();
        }
        _pending_requests.clear();
    }

    // Close sockets
    if (_impl->pub_socket) {
        _impl->pub_socket->close();
        _impl->pub_socket.reset();
    }
    if (_impl->sub_socket) {
        _impl->sub_socket->close();
        _impl->sub_socket.reset();
    }
    if (_impl->heartbeat_socket) {
        _impl->heartbeat_socket->close();
        _impl->heartbeat_socket.reset();
    }
    if (_impl->job_socket) {
        _impl->job_socket->close();
        _impl->job_socket.reset();
    }

    _registered.store(false, std::memory_order_relaxed);
}

void TycheModule::_start_workers() {
    _running.store(true, std::memory_order_relaxed);

    // Step 1: Register with engine via REQ socket
    if (!_register_with_engine()) {
        std::cerr << "[" << _family_name << "] Registration failed." << std::endl;
        _running.store(false, std::memory_order_relaxed);
        return;
    }
    _registered.store(true, std::memory_order_relaxed);

    // Step 2: Set up PUB socket (connect to engine's XSUB port)
    _impl->pub_socket = std::make_unique<zmq::socket_t>(_impl->context, zmq::socket_type::pub);
    _impl->pub_socket->set(zmq::sockopt::linger, 0);
    _impl->pub_socket->set(zmq::sockopt::sndhwm, 10000);
    std::string pub_endpoint = "tcp://" + _engine_endpoint.host + ":" +
                               std::to_string(_impl->engine_sub_port);
    _impl->pub_socket->connect(pub_endpoint);

    // Step 3: Set up SUB socket (connect to engine's XPUB port)
    _impl->sub_socket = std::make_unique<zmq::socket_t>(_impl->context, zmq::socket_type::sub);
    _impl->sub_socket->set(zmq::sockopt::linger, 0);
    _impl->sub_socket->set(zmq::sockopt::rcvhwm, 10000);
    _impl->sub_socket->set(zmq::sockopt::rcvtimeo, 100);
    std::string sub_endpoint = "tcp://" + _engine_endpoint.host + ":" +
                               std::to_string(_impl->engine_pub_port);
    _impl->sub_socket->connect(sub_endpoint);

    // Subscribe to topics based on registered handlers
    _subscribe_to_interfaces();

    // Step 4: Launch event receiver thread
    _impl->event_receiver_thread = std::thread([this]() { _event_receiver_loop(); });

    // Step 5: Launch heartbeat thread (if heartbeat endpoint provided)
    if (_heartbeat_receive_endpoint.has_value()) {
        _impl->heartbeat_socket = std::make_unique<zmq::socket_t>(
            _impl->context, zmq::socket_type::dealer);
        _impl->heartbeat_socket->set(zmq::sockopt::linger, 0);
        std::string hb_endpoint = _heartbeat_receive_endpoint->to_string();
        _impl->heartbeat_socket->connect(hb_endpoint);

        _impl->heartbeat_thread = std::thread([this]() { _heartbeat_loop(); });
    }

    // Step 6: Set up job DEALER socket (if job port provided)
    if (_impl->engine_job_port > 0) {
        _connect_job_socket();
        _impl->job_receiver_thread = std::thread([this]() { _job_receiver_loop(); });
    }

    // Small sleep to let PUB/SUB connections establish
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
}

// ── Registration helpers ───────────────────────────────────────────

void TycheModule::_register_handler(
    const std::string& name,
    Handler handler,
    InterfacePattern pattern,
    DurabilityLevel durability) {
    std::lock_guard<std::mutex> lock(_handlers_lock);

    std::string bare;
    if (name.rfind("on_", 0) == 0) {
        bare = name.substr(3);
    } else if (name.rfind("handle_", 0) == 0) {
        bare = name.substr(7);
    } else {
        bare = name;
    }

    // OPT-3: intern event name once at registration; dispatch uses uint32_t ID
    InternId id = _intern.intern(bare);
    _handlers[id] = {std::move(handler), pattern};

    Interface iface;
    iface.name = name;
    iface.pattern = pattern;
    iface.event_type = bare;
    iface.durability = durability;
    _interfaces.push_back(std::move(iface));
}

void TycheModule::_register_job_handler(
    const std::string& name,
    JobHandler handler,
    DurabilityLevel durability) {
    std::lock_guard<std::mutex> lock(_handlers_lock);

    const std::string bare =
        (name.rfind("handle_", 0) == 0) ? name.substr(7) : name;

    // OPT-3: intern event name once at registration; dispatch uses uint32_t ID
    InternId id = _intern.intern(bare);
    _job_handlers[id] = std::move(handler);

    Interface iface;
    iface.name = name;
    iface.pattern = InterfacePattern::HANDLE;
    iface.event_type = bare;
    iface.durability = durability;
    _interfaces.push_back(std::move(iface));
}

void TycheModule::_register_producer(
    const std::string& name,
    InterfacePattern pattern,
    DurabilityLevel durability) {
    std::lock_guard<std::mutex> lock(_handlers_lock);

    // Strip prefix to get bare event type for routing lookup
    std::string event_type = name;
    if (name.rfind("send_", 0) == 0) {
        event_type = name.substr(5);
    } else if (name.rfind("request_", 0) == 0) {
        event_type = name.substr(8);
    }

    Interface iface;
    iface.name = name;
    iface.pattern = pattern;
    iface.event_type = event_type;
    iface.durability = durability;
    _interfaces.push_back(std::move(iface));
}

// ── Event publishing ───────────────────────────────────────────────

void TycheModule::send_event(
    const std::string& event,
    const Payload& payload,
    std::optional<std::string> recipient) {
    if (!_impl->pub_socket || !_running.load(std::memory_order_relaxed)) {
        return;
    }

    Message m;
    m.msg_type = MessageType::EVENT;
    m.sender = _module_id;
    m.event = event;
    m.payload = payload;
    m.recipient = recipient;
    auto buffer = serialize(m);

    std::lock_guard<std::mutex> lock(_impl->pub_lock);
    zmq::message_t topic_msg(event.data(), event.size());
    zmq::message_t data_msg(buffer.data(), buffer.size());
    _impl->pub_socket->send(topic_msg, zmq::send_flags::sndmore);
    _impl->pub_socket->send(data_msg, zmq::send_flags::none);
}

// ── Internal helpers ────────────────────────────────────────────────

bool TycheModule::_register_with_engine() {
    try {
        zmq::socket_t req_socket(_impl->context, zmq::socket_type::req);
        req_socket.set(zmq::sockopt::linger, 0);
        req_socket.set(zmq::sockopt::rcvtimeo, 5000);
        req_socket.connect(_engine_endpoint.to_string());

        // Build registration message manually via msgpack.
        // Before registration, use family_name as sender.
        msgpack::sbuffer buffer;
        msgpack::packer<msgpack::sbuffer> pk(&buffer);

        pk.pack_map(8);

        pk.pack(std::string("msg_type"));
        pk.pack(std::string("reg"));

        pk.pack(std::string("sender"));
        pk.pack(_family_name);

        pk.pack(std::string("event"));
        pk.pack(std::string("register"));

        pk.pack(std::string("payload"));
        {
            // payload: family_name, interfaces, metadata (no module_id)
            pk.pack_map(3);

            pk.pack(std::string("family_name"));
            pk.pack(_family_name);

            pk.pack(std::string("interfaces"));
            pk.pack_array(static_cast<uint32_t>(_interfaces.size()));
            for (const auto& iface : _interfaces) {
                pk.pack_map(4);
                pk.pack(std::string("name"));
                pk.pack(iface.name);
                pk.pack(std::string("pattern"));
                pk.pack(std::string(interface_pattern_to_str(iface.pattern)));
                pk.pack(std::string("event_type"));
                pk.pack(iface.event_type);
                pk.pack(std::string("durability"));
                pk.pack(static_cast<int>(iface.durability));
            }

            pk.pack(std::string("metadata"));
            pk.pack_map(0);
        }

        pk.pack(std::string("recipient"));
        pk.pack_nil();

        pk.pack(std::string("durability"));
        pk.pack(static_cast<int>(DurabilityLevel::ASYNC_FLUSH));

        pk.pack(std::string("timestamp"));
        pk.pack_nil();

        pk.pack(std::string("correlation_id"));
        pk.pack_nil();

        // Send registration message
        zmq::message_t req_msg(buffer.data(), buffer.size());
        auto send_result = req_socket.send(req_msg, zmq::send_flags::none);
        if (!send_result.has_value()) {
            std::cerr << "[" << _family_name << "] Failed to send registration." << std::endl;
            req_socket.close();
            return false;
        }

        // Receive reply
        zmq::message_t reply;
        auto recv_result = req_socket.recv(reply, zmq::recv_flags::none);
        if (!recv_result.has_value()) {
            std::cerr << "[" << _family_name << "] Registration timeout." << std::endl;
            req_socket.close();
            return false;
        }

        // Deserialize reply
        auto resp = deserialize(reply.data(), reply.size());
        if (resp.msg_type != MessageType::ACK) {
            std::cerr << "[" << _family_name << "] Registration rejected." << std::endl;
            req_socket.close();
            return false;
        }

        // Extract engine-assigned module_id from ACK payload
        auto mid_it = resp.payload.find("module_id");
        if (mid_it != resp.payload.end()) {
            _module_id = std::any_cast<std::string>(mid_it->second);
        } else {
            std::cerr << "[" << _family_name << "] ACK missing module_id." << std::endl;
            req_socket.close();
            return false;
        }

        // Extract ports from reply payload
        auto pub_port_it = resp.payload.find("event_pub_port");
        auto sub_port_it = resp.payload.find("event_sub_port");
        auto job_port_it = resp.payload.find("job_port");
        if (pub_port_it != resp.payload.end() && sub_port_it != resp.payload.end()) {
            _impl->engine_pub_port = std::any_cast<int>(pub_port_it->second);
            _impl->engine_sub_port = std::any_cast<int>(sub_port_it->second);
            if (job_port_it != resp.payload.end()) {
                _impl->engine_job_port = std::any_cast<int>(job_port_it->second);
            }
        } else {
            std::cerr << "[" << _family_name << "] Missing port info in ACK." << std::endl;
            req_socket.close();
            return false;
        }

        std::cerr << "[" << _module_id << "] Registered with engine"
                  << " (family_name=" << _family_name << ")" << std::endl;

        req_socket.close();
        return true;

    } catch (const zmq::error_t& e) {
        std::cerr << "[" << _family_name << "] ZMQ error during registration: "
                  << e.what() << std::endl;
        return false;
    } catch (const std::exception& e) {
        std::cerr << "[" << _family_name << "] Error during registration: "
                  << e.what() << std::endl;
        return false;
    }
}

void TycheModule::_subscribe_to_interfaces() {
    std::lock_guard<std::mutex> lock(_handlers_lock);
    for (const auto& [topic_id, _] : _handlers) {
        // OPT-3: resolve interned ID back to string for ZMQ subscribe
        std::string_view topic = _intern.resolve(topic_id);
        _impl->sub_socket->set(zmq::sockopt::subscribe, topic);
    }
}

void TycheModule::_event_receiver_loop() {
    while (_running.load(std::memory_order_relaxed)) {
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(*_impl->sub_socket,
                                              std::back_inserter(frames));
            if (!result.has_value() || frames.size() < 2) {
                continue;  // timeout or incomplete message
            }

            // frames[0] = topic, frames[1] = msgpack message
            std::string topic(static_cast<const char*>(frames[0].data()),
                              frames[0].size());

            auto msg = deserialize(frames[1].data(), frames[1].size());

            // Ignore self-sent messages
            if (msg.sender == _module_id) {
                continue;
            }

            // Dispatch to handler
            _dispatch(topic, msg.payload);

        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM || e.num() == EINTR) {
                break;  // Context terminated or interrupted
            }
            // EAGAIN from timeout is handled by recv_multipart returning empty
        } catch (...) {
            // Swallow unexpected exceptions in receiver loop
        }
    }
}

void TycheModule::_heartbeat_loop() {
    while (_running.load(std::memory_order_relaxed)) {
        try {
            Message hb_msg;
            hb_msg.msg_type = MessageType::HEARTBEAT;
            hb_msg.sender = _module_id;
            hb_msg.event = "heartbeat";
            hb_msg.payload["status"] = std::string("alive");
            auto buffer = serialize(hb_msg);

            zmq::message_t msg(buffer.data(), buffer.size());
            _impl->heartbeat_socket->send(msg, zmq::send_flags::none);

        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        } catch (...) {
            // Swallow
        }

        // Sleep for 1 second in small increments to allow quick shutdown
        for (int i = 0; i < 10 && _running.load(std::memory_order_relaxed); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}

void TycheModule::_dispatch(const std::string& topic, const Payload& payload) {
    const std::string lookup =
        (topic.rfind("on_", 0) == 0) ? topic.substr(3) : topic;

    // OPT-3: resolve string to interned ID for O(1) integer-key lookup
    InternId id = _intern.lookup(lookup);
    if (id == INVALID_INTERN_ID) return;

    Handler handler;
    {
        std::lock_guard<std::mutex> lock(_handlers_lock);
        auto it = _handlers.find(id);
        if (it == _handlers.end()) {
            return;
        }
        handler = it->second.first;
    }
    if (!handler) return;

    try {
        handler(payload);
    } catch (...) {
        // Swallow handler exceptions -- mirrors Python's try/except in _dispatch.
    }
}

// ── Job socket implementation ────────────────────────────────────────

void TycheModule::_connect_job_socket() {
    _impl->job_socket = std::make_unique<zmq::socket_t>(
        _impl->context, zmq::socket_type::dealer);
    _impl->job_socket->set(zmq::sockopt::linger, 0);
    _impl->job_socket->set(zmq::sockopt::routing_id,
                           zmq::buffer(_module_id));
    _impl->job_socket->set(zmq::sockopt::rcvtimeo, 100);

    std::string job_endpoint = "tcp://" + _engine_endpoint.host + ":" +
                               std::to_string(_impl->engine_job_port);
    _impl->job_socket->connect(job_endpoint);
}

std::string TycheModule::_generate_correlation_id() {
    // Generate a pseudo-UUID: 32 hex chars in 8-4-4-4-12 format.
    static thread_local std::mt19937 rng{std::random_device{}()};
    std::uniform_int_distribution<unsigned int> dist(0, 15);

    auto hex_block = [&](int n) {
        std::string s;
        s.reserve(static_cast<std::string::size_type>(n));
        for (int i = 0; i < n; ++i) {
            const char c = "0123456789abcdef"[dist(rng)];
            s += c;
        }
        return s;
    };

    return hex_block(8) + "-" + hex_block(4) + "-" +
           hex_block(4) + "-" + hex_block(4) + "-" + hex_block(12);
}

Payload TycheModule::request_event(
    const std::string& event,
    const Payload& payload,
    float timeout) {
    if (!_impl->job_socket || !_running.load(std::memory_order_relaxed)) {
        throw std::runtime_error(
            "[" + _module_id + "] Cannot request: job socket not connected");
    }

    std::string correlation_id = _generate_correlation_id();

    // Create pending request entry
    auto pending = std::make_shared<PendingRequest>();
    {
        std::lock_guard<std::mutex> lock(_pending_lock);
        _pending_requests[correlation_id] = pending;
    }

    // Serialize and send: [b"", topic, message]
    Message req_msg;
    req_msg.msg_type = MessageType::REQUEST;
    req_msg.sender = _module_id;
    req_msg.event = event;
    req_msg.payload = payload;
    req_msg.correlation_id = correlation_id;
    auto buffer = serialize(req_msg);

    {
        std::lock_guard<std::mutex> lock(_impl->job_lock);
        zmq::message_t empty(0);
        zmq::message_t topic_msg(event.data(), event.size());
        zmq::message_t data_msg(buffer.data(), buffer.size());
        _impl->job_socket->send(empty, zmq::send_flags::sndmore);
        _impl->job_socket->send(topic_msg, zmq::send_flags::sndmore);
        _impl->job_socket->send(data_msg, zmq::send_flags::none);
    }

    // Wait for response with timeout
    {
        std::unique_lock<std::mutex> lock(_pending_lock);
        bool got_result = pending->cv.wait_for(
            lock,
            std::chrono::milliseconds(static_cast<int>(timeout * 1000)),
            [&]() { return pending->ready; });

        _pending_requests.erase(correlation_id);

        if (!got_result) {
            throw std::runtime_error(
                "Job request '" + event + "' timed out after " +
                std::to_string(timeout) + "s");
        }
    }

    return pending->result;
}

void TycheModule::_job_receiver_loop() {
    while (_running.load(std::memory_order_relaxed)) {
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(*_impl->job_socket,
                                              std::back_inserter(frames));
            if (!result.has_value() || frames.size() < 3) {
                continue;  // timeout or incomplete
            }

            // Frames from ROUTER: [b"", topic, message]
            auto msg = deserialize(frames[2].data(), frames[2].size());

            if (msg.msg_type == MessageType::REQUEST) {
                // Incoming job assignment -- dispatch to handler
                _handle_job_request(msg.event, msg.payload, msg.correlation_id);
            } else if (msg.msg_type == MessageType::RESPONSE) {
                // Response to our outgoing request
                _handle_job_response(msg.payload, msg.correlation_id);
            }

        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM || e.num() == EINTR) {
                break;
            }
            // EAGAIN from timeout is handled by recv_multipart returning empty
        } catch (...) {
            // Swallow unexpected exceptions in job receiver loop
        }
    }
}

void TycheModule::_handle_job_request(
    const std::string& event,
    const Payload& payload,
    const std::optional<std::string>& correlation_id) {

    // OPT-3: resolve string to interned ID for O(1) integer-key lookup
    InternId event_id = _intern.lookup(event);

    JobHandler handler;
    {
        std::lock_guard<std::mutex> lock(_handlers_lock);
        auto it = _job_handlers.find(event_id);
        if (it == _job_handlers.end()) {
            // No handler -- send error response
            Payload err;
            err["error"] = std::string("No handler for job '" + event + "'");
            Message err_resp;
            err_resp.msg_type = MessageType::RESPONSE;
            err_resp.sender = _module_id;
            err_resp.event = event;
            err_resp.payload = err;
            err_resp.correlation_id = correlation_id;
            auto buffer = serialize(err_resp);

            std::lock_guard<std::mutex> jlock(_impl->job_lock);
            zmq::message_t empty(0);
            zmq::message_t topic_msg(event.data(), event.size());
            zmq::message_t data_msg(buffer.data(), buffer.size());
            _impl->job_socket->send(empty, zmq::send_flags::sndmore);
            _impl->job_socket->send(topic_msg, zmq::send_flags::sndmore);
            _impl->job_socket->send(data_msg, zmq::send_flags::none);
            return;
        }
        handler = it->second;
    }

    Payload response_payload;
    try {
        Payload result = handler(payload);
        response_payload["result"] = std::any(std::move(result));
    } catch (const std::exception& e) {
        response_payload["error"] = std::string(e.what());
    } catch (...) {
        response_payload["error"] = std::string("Unknown handler error");
    }

    Message resp_msg;
    resp_msg.msg_type = MessageType::RESPONSE;
    resp_msg.sender = _module_id;
    resp_msg.event = event;
    resp_msg.payload = response_payload;
    resp_msg.correlation_id = correlation_id;
    auto buffer = serialize(resp_msg);

    std::lock_guard<std::mutex> jlock(_impl->job_lock);
    zmq::message_t empty(0);
    zmq::message_t topic_msg(event.data(), event.size());
    zmq::message_t data_msg(buffer.data(), buffer.size());
    _impl->job_socket->send(empty, zmq::send_flags::sndmore);
    _impl->job_socket->send(topic_msg, zmq::send_flags::sndmore);
    _impl->job_socket->send(data_msg, zmq::send_flags::none);
}

void TycheModule::_handle_job_response(
    const Payload& payload,
    const std::optional<std::string>& correlation_id) {
    if (!correlation_id.has_value()) return;

    std::lock_guard<std::mutex> lock(_pending_lock);
    auto it = _pending_requests.find(*correlation_id);
    if (it == _pending_requests.end()) {
        std::cerr << "[" << _module_id
                  << "] Received response for unknown correlation_id="
                  << *correlation_id << std::endl;
        return;
    }

    it->second->result = payload;
    it->second->ready = true;
    it->second->cv.notify_all();
}

}  // namespace tyche
