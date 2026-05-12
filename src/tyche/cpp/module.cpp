// Full ZMQ-based implementation of tyche::TycheModule.
//
// Mirrors the logic in src/tyche/module.py:
//   - REGISTER over a one-shot REQ socket; capture engine_pub/sub_port
//   - PUB socket  -> engine XSUB (event publishing)
//   - SUB socket  <- engine XPUB (event reception, dispatch loop)
//   - DEALER socket for heartbeats

#include "tyche/cpp/module.h"

#include <zmq.hpp>
#include <zmq_addon.hpp>
#include <msgpack.hpp>

#include <chrono>
#include <iostream>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace tyche {

// ── msgpack serialization helpers ─────────────────────────────────────

namespace {

// Pack a std::any value into a msgpack::packer.
// Supports: string, int, double, bool, nullptr, and nested Payload.
void pack_any(msgpack::packer<msgpack::sbuffer>& pk, const std::any& value) {
    if (!value.has_value()) {
        pk.pack_nil();
    } else if (value.type() == typeid(std::string)) {
        pk.pack(std::any_cast<std::string>(value));
    } else if (value.type() == typeid(const char*)) {
        pk.pack(std::string(std::any_cast<const char*>(value)));
    } else if (value.type() == typeid(int)) {
        pk.pack(std::any_cast<int>(value));
    } else if (value.type() == typeid(int64_t)) {
        pk.pack(std::any_cast<int64_t>(value));
    } else if (value.type() == typeid(uint64_t)) {
        pk.pack(std::any_cast<uint64_t>(value));
    } else if (value.type() == typeid(double)) {
        pk.pack(std::any_cast<double>(value));
    } else if (value.type() == typeid(float)) {
        pk.pack(static_cast<double>(std::any_cast<float>(value)));
    } else if (value.type() == typeid(bool)) {
        pk.pack(std::any_cast<bool>(value));
    } else if (value.type() == typeid(Payload)) {
        const auto& map = std::any_cast<const Payload&>(value);
        pk.pack_map(static_cast<uint32_t>(map.size()));
        for (const auto& [k, v] : map) {
            pk.pack(k);
            pack_any(pk, v);
        }
    } else if (value.type() == typeid(std::vector<std::string>)) {
        const auto& vec = std::any_cast<const std::vector<std::string>&>(value);
        pk.pack_array(static_cast<uint32_t>(vec.size()));
        for (const auto& s : vec) {
            pk.pack(s);
        }
    } else {
        // Unknown type -- pack as nil
        pk.pack_nil();
    }
}

// Convert a msgpack::object to std::any.
std::any unpack_object(const msgpack::object& obj) {
    switch (obj.type) {
        case msgpack::type::NIL:
            return std::any{};
        case msgpack::type::BOOLEAN:
            return std::any{obj.via.boolean};
        case msgpack::type::POSITIVE_INTEGER:
            return std::any{static_cast<int>(obj.via.u64)};
        case msgpack::type::NEGATIVE_INTEGER:
            return std::any{static_cast<int>(obj.via.i64)};
        case msgpack::type::FLOAT32:
        case msgpack::type::FLOAT64:
            return std::any{obj.via.f64};
        case msgpack::type::STR:
            return std::any{std::string(obj.via.str.ptr, obj.via.str.size)};
        case msgpack::type::MAP: {
            Payload map;
            for (uint32_t i = 0; i < obj.via.map.size; ++i) {
                const auto& kv = obj.via.map.ptr[i];
                std::string key(kv.key.via.str.ptr, kv.key.via.str.size);
                map[key] = unpack_object(kv.val);
            }
            return std::any{std::move(map)};
        }
        case msgpack::type::ARRAY: {
            std::vector<std::string> arr;
            for (uint32_t i = 0; i < obj.via.array.size; ++i) {
                const auto& elem = obj.via.array.ptr[i];
                if (elem.type == msgpack::type::STR) {
                    arr.emplace_back(elem.via.str.ptr, elem.via.str.size);
                }
            }
            return std::any{std::move(arr)};
        }
        default:
            return std::any{};
    }
}

// Serialize a Message into a msgpack buffer.
// Format matches Python: {msg_type, sender, event, payload, recipient, durability, timestamp, correlation_id}
msgpack::sbuffer serialize_message(
    MessageType msg_type,
    const std::string& sender,
    const std::string& event,
    const Payload& payload,
    const std::optional<std::string>& recipient = std::nullopt,
    DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH,
    std::optional<double> timestamp = std::nullopt,
    const std::optional<std::string>& correlation_id = std::nullopt) {

    msgpack::sbuffer buffer;
    msgpack::packer<msgpack::sbuffer> pk(&buffer);

    pk.pack_map(8);

    pk.pack(std::string("msg_type"));
    pk.pack(std::string(message_type_to_str(msg_type)));

    pk.pack(std::string("sender"));
    pk.pack(sender);

    pk.pack(std::string("event"));
    pk.pack(event);

    pk.pack(std::string("payload"));
    pk.pack_map(static_cast<uint32_t>(payload.size()));
    for (const auto& [k, v] : payload) {
        pk.pack(k);
        pack_any(pk, v);
    }

    pk.pack(std::string("recipient"));
    if (recipient.has_value()) {
        pk.pack(*recipient);
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("durability"));
    pk.pack(static_cast<int>(durability));

    pk.pack(std::string("timestamp"));
    if (timestamp.has_value()) {
        pk.pack(*timestamp);
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("correlation_id"));
    if (correlation_id.has_value()) {
        pk.pack(*correlation_id);
    } else {
        pk.pack_nil();
    }

    return buffer;
}

// Deserialize a msgpack buffer into components.
struct DeserializedMessage {
    MessageType msg_type = MessageType::EVENT;
    std::string sender;
    std::string event;
    Payload payload;
    std::optional<std::string> recipient;
    DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH;
};

DeserializedMessage deserialize_message(const void* data, size_t size) {
    DeserializedMessage msg;
    msgpack::object_handle oh = msgpack::unpack(static_cast<const char*>(data), size);
    const msgpack::object& obj = oh.get();

    if (obj.type != msgpack::type::MAP) return msg;

    for (uint32_t i = 0; i < obj.via.map.size; ++i) {
        const auto& kv = obj.via.map.ptr[i];
        if (kv.key.type != msgpack::type::STR) continue;

        std::string key(kv.key.via.str.ptr, kv.key.via.str.size);

        if (key == "msg_type" && kv.val.type == msgpack::type::STR) {
            std::string val(kv.val.via.str.ptr, kv.val.via.str.size);
            msg.msg_type = message_type_from_str(val);
        } else if (key == "sender" && kv.val.type == msgpack::type::STR) {
            msg.sender = std::string(kv.val.via.str.ptr, kv.val.via.str.size);
        } else if (key == "event" && kv.val.type == msgpack::type::STR) {
            msg.event = std::string(kv.val.via.str.ptr, kv.val.via.str.size);
        } else if (key == "payload" && kv.val.type == msgpack::type::MAP) {
            for (uint32_t j = 0; j < kv.val.via.map.size; ++j) {
                const auto& pkv = kv.val.via.map.ptr[j];
                if (pkv.key.type == msgpack::type::STR) {
                    std::string pkey(pkv.key.via.str.ptr, pkv.key.via.str.size);
                    msg.payload[pkey] = unpack_object(pkv.val);
                }
            }
        } else if (key == "recipient") {
            if (kv.val.type == msgpack::type::STR) {
                msg.recipient = std::string(kv.val.via.str.ptr, kv.val.via.str.size);
            }
        } else if (key == "durability") {
            if (kv.val.type == msgpack::type::POSITIVE_INTEGER ||
                kv.val.type == msgpack::type::NEGATIVE_INTEGER) {
                msg.durability = static_cast<DurabilityLevel>(
                    kv.val.type == msgpack::type::POSITIVE_INTEGER
                        ? static_cast<int>(kv.val.via.u64)
                        : static_cast<int>(kv.val.via.i64));
            }
        }
    }
    return msg;
}

}  // namespace

// ── PIMPL: ZMQ state ──────────────────────────────────────────────────

struct TycheModule::Impl {
    zmq::context_t context{1};
    std::unique_ptr<zmq::socket_t> pub_socket;
    std::unique_ptr<zmq::socket_t> sub_socket;
    std::unique_ptr<zmq::socket_t> heartbeat_socket;

    std::thread event_receiver_thread;
    std::thread heartbeat_thread;

    int engine_pub_port = 0;  // engine XPUB port (we SUB here)
    int engine_sub_port = 0;  // engine XSUB port (we PUB here)

    std::mutex pub_lock;  // thread-safe PUB sends
};

// ── Construction / destruction ─────────────────────────────────────

TycheModule::TycheModule(
    Endpoint engine_endpoint,
    std::string module_id,
    std::optional<Endpoint> heartbeat_receive_endpoint)
    : _module_id(std::move(module_id)),
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

    _registered.store(false, std::memory_order_relaxed);
}

void TycheModule::_start_workers() {
    _running.store(true, std::memory_order_relaxed);

    // Step 1: Register with engine via REQ socket
    if (!_register_with_engine()) {
        std::cerr << "[" << _module_id << "] Registration failed." << std::endl;
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

    const std::string bare =
        (name.rfind("on_", 0) == 0) ? name.substr(3) : name;

    _handlers[bare] = {std::move(handler), pattern};

    Interface iface;
    iface.name = name;
    iface.pattern = pattern;
    iface.event_type = bare;
    iface.durability = durability;
    _interfaces.push_back(std::move(iface));
}

void TycheModule::_register_producer(
    const std::string& name,
    InterfacePattern pattern,
    DurabilityLevel durability) {
    std::lock_guard<std::mutex> lock(_handlers_lock);

    Interface iface;
    iface.name = name;
    iface.pattern = pattern;
    iface.event_type = name;
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

    auto buffer = serialize_message(
        MessageType::EVENT,
        _module_id,
        event,
        payload,
        recipient);

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

        // Build interfaces payload
        Payload reg_payload;
        reg_payload["module_id"] = std::string(_module_id);

        // Build interfaces list as a vector of Payload maps
        msgpack::sbuffer buffer;
        msgpack::packer<msgpack::sbuffer> pk(&buffer);

        pk.pack_map(8);

        pk.pack(std::string("msg_type"));
        pk.pack(std::string("reg"));

        pk.pack(std::string("sender"));
        pk.pack(_module_id);

        pk.pack(std::string("event"));
        pk.pack(std::string("register"));

        pk.pack(std::string("payload"));
        {
            // payload is a map with module_id, interfaces, metadata
            pk.pack_map(3);

            pk.pack(std::string("module_id"));
            pk.pack(_module_id);

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
            std::cerr << "[" << _module_id << "] Failed to send registration." << std::endl;
            req_socket.close();
            return false;
        }

        // Receive reply
        zmq::message_t reply;
        auto recv_result = req_socket.recv(reply, zmq::recv_flags::none);
        if (!recv_result.has_value()) {
            std::cerr << "[" << _module_id << "] Registration timeout." << std::endl;
            req_socket.close();
            return false;
        }

        // Deserialize reply
        auto resp = deserialize_message(reply.data(), reply.size());
        if (resp.msg_type != MessageType::ACK) {
            std::cerr << "[" << _module_id << "] Registration rejected." << std::endl;
            req_socket.close();
            return false;
        }

        // Extract ports from reply payload
        auto pub_port_it = resp.payload.find("event_pub_port");
        auto sub_port_it = resp.payload.find("event_sub_port");
        if (pub_port_it != resp.payload.end() && sub_port_it != resp.payload.end()) {
            _impl->engine_pub_port = std::any_cast<int>(pub_port_it->second);
            _impl->engine_sub_port = std::any_cast<int>(sub_port_it->second);
        } else {
            std::cerr << "[" << _module_id << "] Missing port info in ACK." << std::endl;
            req_socket.close();
            return false;
        }

        req_socket.close();
        return true;

    } catch (const zmq::error_t& e) {
        std::cerr << "[" << _module_id << "] ZMQ error during registration: "
                  << e.what() << std::endl;
        return false;
    } catch (const std::exception& e) {
        std::cerr << "[" << _module_id << "] Error during registration: "
                  << e.what() << std::endl;
        return false;
    }
}

void TycheModule::_subscribe_to_interfaces() {
    std::lock_guard<std::mutex> lock(_handlers_lock);
    for (const auto& [topic, _] : _handlers) {
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

            auto msg = deserialize_message(frames[1].data(), frames[1].size());

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
            Payload hb_payload;
            hb_payload["status"] = std::string("alive");

            auto buffer = serialize_message(
                MessageType::HEARTBEAT,
                _module_id,
                "heartbeat",
                hb_payload);

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

    Handler handler;
    {
        std::lock_guard<std::mutex> lock(_handlers_lock);
        auto it = _handlers.find(lookup);
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

}  // namespace tyche
