// TycheEngine - Central event/job routing engine implementation.
//
// Mirrors Python src/tyche/engine.py with 10 worker threads.
// All ZMQ sockets are created and used within their owning thread.
// Inter-thread communication uses lock-protected queues.

#include "tyche/cpp/engine/engine.h"
#include "tyche/cpp/engine/shared_memory_bridge.h"

#include <zmq.hpp>
#include <zmq_addon.hpp>
#include <msgpack.hpp>

#include <algorithm>
#include <chrono>
#include <functional>
#include <iostream>

namespace tyche {

// ── ZMQ Context PIMPL ───────────────────────────────────────────────

struct TycheEngine::ZmqContext {
    zmq::context_t ctx{1};
};

// ── Helpers (file-local) ────────────────────────────────────────────

namespace {

void zmq_send_frames(zmq::socket_t& socket,
                     const std::vector<std::vector<uint8_t>>& frames) {
    for (size_t i = 0; i < frames.size(); ++i) {
        auto flags = (i + 1 < frames.size())
                         ? zmq::send_flags::sndmore
                         : zmq::send_flags::none;
        socket.send(zmq::message_t(frames[i].data(), frames[i].size()), flags);
    }
}

std::vector<uint8_t> to_bytes(const zmq::message_t& msg) {
    auto* p = static_cast<const uint8_t*>(msg.data());
    return {p, p + msg.size()};
}

std::vector<uint8_t> str_to_bytes(const std::string& s) {
    return {s.begin(), s.end()};
}

std::string bytes_to_str(const std::vector<uint8_t>& v) {
    return {v.begin(), v.end()};
}

}  // anonymous namespace

// ── Time helper ─────────────────────────────────────────────────────

double TycheEngine::_now() {
    auto tp = std::chrono::system_clock::now();
    return std::chrono::duration<double>(tp.time_since_epoch()).count();
}

// ── Constructor / Destructor ────────────────────────────────────────

TycheEngine::TycheEngine(
    Endpoint registration_endpoint,
    Endpoint event_endpoint,
    Endpoint heartbeat_endpoint,
    Endpoint heartbeat_recv_endpoint,
    Endpoint admin_endpoint,
    Endpoint job_endpoint,
    int queue_capacity,
    std::string data_dir)
    : _registration_endpoint(std::move(registration_endpoint)),
      _event_endpoint(std::move(event_endpoint)),
      _event_sub_endpoint(_event_endpoint.host, _event_endpoint.port + 1),
      _heartbeat_endpoint(std::move(heartbeat_endpoint)),
      _heartbeat_recv_endpoint(std::move(heartbeat_recv_endpoint)),
      _admin_endpoint(std::move(admin_endpoint)),
      _job_endpoint(std::move(job_endpoint)),
      _queue_capacity(queue_capacity),
      _heartbeat_manager(HEARTBEAT_INTERVAL_SEC, HEARTBEAT_LIVENESS_DEFAULT),
      _dead_letter_store(data_dir + "/dead_letters"),
      _shm_bridge(std::make_unique<SharedMemoryBridge>()) {
    _start_time = _now();
}

TycheEngine::~TycheEngine() {
    if (_running.load()) stop();
}

// ── Lifecycle ───────────────────────────────────────────────────────

void TycheEngine::start_nonblocking() {
    _zmq_ctx = std::make_unique<ZmqContext>();
    _running.store(true, std::memory_order_release);

    _threads.emplace_back(&TycheEngine::_registration_worker, this);
    _threads.emplace_back(&TycheEngine::_registration_egress_worker, this);
    _threads.emplace_back(&TycheEngine::_heartbeat_worker, this);
    _threads.emplace_back(&TycheEngine::_heartbeat_receive_worker, this);
    _threads.emplace_back(&TycheEngine::_monitor_worker, this);
    _threads.emplace_back(&TycheEngine::_event_proxy_worker, this);
    _threads.emplace_back(&TycheEngine::_event_egress_worker, this);
    _threads.emplace_back(&TycheEngine::_admin_worker, this);
    _threads.emplace_back(&TycheEngine::_job_router_worker, this);
    _threads.emplace_back(&TycheEngine::_job_timeout_worker, this);

    // Start shared memory bridge if configured
    if (_shm_bridge) {
        _shm_bridge->start(this);
    }

    std::cerr << "[TycheEngine] All 10 workers started\n"
              << "[TycheEngine] Endpoints:"
              << " reg=" << _registration_endpoint.to_string()
              << " event=" << _event_endpoint.to_string()
              << " hb=" << _heartbeat_endpoint.to_string()
              << " hb_recv=" << _heartbeat_recv_endpoint.to_string()
              << " admin=" << _admin_endpoint.to_string()
              << " job=" << _job_endpoint.to_string() << std::endl;
}

void TycheEngine::run() {
    start_nonblocking();
    while (_running.load(std::memory_order_relaxed)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

void TycheEngine::stop() {
    if (!_running.load()) return;
    std::cerr << "[TycheEngine] Stopping..." << std::endl;
    _running.store(false, std::memory_order_release);

    // Stop shared memory bridge first (before ZMQ context is destroyed)
    if (_shm_bridge) {
        _shm_bridge->stop();
    }

    _egress_wakeup_cv.notify_all();
    _reg_in_cv.notify_all();

    for (auto& t : _threads) {
        if (t.joinable()) t.join();
    }
    _threads.clear();
    _zmq_ctx.reset();
    std::cerr << "[TycheEngine] Shutdown complete" << std::endl;
}

// ── Event injection (for SharedMemoryBridge) ────────────────────────

void TycheEngine::inject_event(const std::string& topic,
                                const std::vector<uint8_t>& message_data) {
    // Build Frame-based QueueItem and enqueue to topic queue
    std::vector<Frame> frames;
    frames.emplace_back(reinterpret_cast<const uint8_t*>(topic.data()), topic.size());
    frames.emplace_back(message_data.data(), message_data.size());

    auto q = _topic_queues.get_or_create(topic, static_cast<size_t>(_queue_capacity));
    q->put(QueueItem(_now(), std::move(frames)));
    _topic_queues.touch(topic, _now());

    {
        std::lock_guard lock(_egress_wakeup_lock);
        _egress_wakeup_flag = true;
    }
    _egress_wakeup_cv.notify_one();
}

// ── Module ID generation ────────────────────────────────────────────

std::string TycheEngine::_create_module_id(const std::string& family_name) {
    for (int attempt = 0; attempt < 100; ++attempt) {
        std::string id = ModuleId::generate(family_name);
        if (_modules.find(id) == _modules.end()) return id;
    }
    return ModuleId::generate(family_name);
}

// ── Module Registration ─────────────────────────────────────────────

void TycheEngine::register_module(const ModuleInfo& info) {
    {
        std::unique_lock lock(_modules_lock);
        _modules[info.module_id] = info;

        for (const auto& iface : info.interfaces) {
            // OPT-3: Intern topic strings once at registration to eliminate
            // repeated hashing/comparison on hot lookup paths.
            InternId topic_id = _intern.intern(iface.event_type);

            // Ensure topic queue exists (OPT-2: sharded map, no global lock)
            _topic_queues.get_or_create(iface.event_type, static_cast<size_t>(_queue_capacity));

            if (iface.pattern == InterfacePattern::ON) {
                auto& subs = _topic_subscribers[topic_id];
                if (std::find(subs.begin(), subs.end(), info.module_id) == subs.end())
                    subs.push_back(info.module_id);
            } else if (iface.pattern == InterfacePattern::SEND) {
                auto& prods = _topic_producers[topic_id];
                if (std::find(prods.begin(), prods.end(), info.module_id) == prods.end())
                    prods.push_back(info.module_id);
            } else if (iface.pattern == InterfacePattern::HANDLE) {
                auto& handlers = _job_handlers[topic_id];
                if (std::find(handlers.begin(), handlers.end(), info.module_id) == handlers.end())
                    handlers.push_back(info.module_id);
                {
                    std::lock_guard jlock(_job_lock);
                    if (_job_round_robin.find(topic_id) == _job_round_robin.end())
                        _job_round_robin[topic_id] = 0;
                }
                std::cerr << "[TycheEngine] Registered job handler: " << info.module_id
                          << " for '" << iface.event_type << "'" << std::endl;
            } else if (iface.pattern == InterfacePattern::REQUEST) {
                auto& prods = _topic_producers[topic_id];
                if (std::find(prods.begin(), prods.end(), info.module_id) == prods.end())
                    prods.push_back(info.module_id);
            }
        }
    }
    _heartbeat_manager.register_module(info.module_id);
}

void TycheEngine::unregister_module(const std::string& module_id) {
    {
        std::unique_lock lock(_modules_lock);
        if (_modules.find(module_id) == _modules.end()) return;

        for (auto& [t, subs] : _topic_subscribers)
            subs.erase(std::remove(subs.begin(), subs.end(), module_id), subs.end());
        for (auto& [t, prods] : _topic_producers)
            prods.erase(std::remove(prods.begin(), prods.end(), module_id), prods.end());
        for (auto& [t, handlers] : _job_handlers)
            handlers.erase(std::remove(handlers.begin(), handlers.end(), module_id), handlers.end());

        _unavailable_handlers.erase(module_id);
        _module_availability.erase(module_id);
        _modules.erase(module_id);
    }

    {
        std::lock_guard jlock(_job_lock);
        for (auto& [cid, info] : _job_tracking) {
            if (info.handler_id == module_id) {
                info.handler_id.clear();
                info.dispatch_time = 0.0;
            }
        }
    }

    _heartbeat_manager.unregister(module_id);
    std::cerr << "[TycheEngine] Module " << module_id << " unregistered" << std::endl;
}

// ── Handler availability ────────────────────────────────────────────

bool TycheEngine::_is_handler_available(const std::string& module_id,
                                         const std::string& topic) const {
    auto uit = _unavailable_handlers.find(module_id);
    if (uit != _unavailable_handlers.end() && uit->second.count(topic))
        return false;
    auto ait = _module_availability.find(module_id);
    if (ait != _module_availability.end()) {
        auto tit = ait->second.find(topic);
        if (tit != ait->second.end() && !tit->second) return false;
    }
    return true;
}

// ── Enqueue from XSUB ──────────────────────────────────────────────

// OPT-2: Sharded topic queue lookup eliminates global mutex contention.
// The event proxy thread (single writer) acquires only a per-bucket spinlock.
// Hashing spreads topics across 256 buckets; collisions are rare and short.
void TycheEngine::_enqueue_from_xsub(
    const std::vector<std::vector<uint8_t>>& frames) {
    if (frames.size() < 2) return;
    std::string topic(frames[0].begin(), frames[0].end());

    auto q = _topic_queues.get_or_create(topic, static_cast<size_t>(_queue_capacity));
    // Convert to SSO-optimized Frame storage to eliminate to_bytes allocation
    std::vector<Frame> fframes;
    fframes.reserve(frames.size());
    for (const auto& f : frames) {
        fframes.emplace_back(f.data(), f.size());
    }
    q->put(QueueItem(_now(), std::move(fframes)));
    _topic_queues.touch(topic, _now());

    {
        std::lock_guard lock(_egress_wakeup_lock);
        _egress_wakeup_flag = true;
    }
    _egress_wakeup_cv.notify_one();
}

// ══════════════════════════════════════════════════════════════════════
// Worker Thread Implementations
// ══════════════════════════════════════════════════════════════════════

// ── 1. Registration Worker (owns ROUTER socket) ─────────────────────

void TycheEngine::_registration_worker() {
    zmq::socket_t socket(_zmq_ctx->ctx, zmq::socket_type::router);
    socket.set(zmq::sockopt::linger, 0);
    socket.set(zmq::sockopt::rcvtimeo, 50);
    socket.bind(_registration_endpoint.to_string());

    while (_running.load(std::memory_order_relaxed)) {
        // Receive incoming registration requests
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(socket, std::back_inserter(frames));
            if (result.has_value() && frames.size() >= 2) {
                auto identity = to_bytes(frames[0]);
                const auto& msg_f = (frames.size() >= 3 && frames[1].size() == 0)
                                        ? frames[2] : frames[1];
                {
                    std::lock_guard lock(_reg_in_lock);
                    _reg_in_queue.push({std::move(identity), to_bytes(msg_f)});
                }
                _reg_in_cv.notify_one();
            }
        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        }

        // Send any pending replies
        {
            std::lock_guard lock(_reg_out_lock);
            while (!_reg_out_queue.empty()) {
                try { zmq_send_frames(socket, _reg_out_queue.front().frames); }
                catch (...) {}
                _reg_out_queue.pop();
            }
        }
    }
    socket.close();
}

// ── 2. Registration Egress Worker ───────────────────────────────────

void TycheEngine::_registration_egress_worker() {
    while (_running.load(std::memory_order_relaxed)) {
        RegRequest req;
        {
            std::unique_lock lock(_reg_in_lock);
            _reg_in_cv.wait_for(lock, std::chrono::milliseconds(100),
                [this]() { return !_reg_in_queue.empty() || !_running.load(); });
            if (_reg_in_queue.empty()) continue;
            req = std::move(_reg_in_queue.front());
            _reg_in_queue.pop();
        }

        try {
            Message msg = deserialize(req.msg_data.data(), req.msg_data.size());
            if (msg.msg_type != MessageType::REGISTER) continue;

            // Extract family_name
            std::string family_name;
            auto fn_it = msg.payload.find("family_name");
            if (fn_it != msg.payload.end())
                family_name = std::any_cast<std::string>(fn_it->second);
            else
                family_name = msg.sender.empty() ? "unknown" : msg.sender;

            // Generate unique module_id
            std::string module_id;
            {
                std::shared_lock rlock(_modules_lock);
                module_id = _create_module_id(family_name);
            }

            // Parse interfaces from raw msgpack (because unpack_object cannot
            // handle arrays of maps; it only handles arrays of strings).
            std::vector<Interface> interfaces;
            {
                msgpack::object_handle oh = msgpack::unpack(
                    reinterpret_cast<const char*>(req.msg_data.data()),
                    req.msg_data.size());
                const auto& obj = oh.get();
                if (obj.type == msgpack::type::MAP) {
                    for (uint32_t i = 0; i < obj.via.map.size; ++i) {
                        const auto& kv = obj.via.map.ptr[i];
                        if (kv.key.type != msgpack::type::STR) continue;
                        std::string key(kv.key.via.str.ptr, kv.key.via.str.size);
                        if (key != "payload" || kv.val.type != msgpack::type::MAP) continue;

                        for (uint32_t j = 0; j < kv.val.via.map.size; ++j) {
                            const auto& pkv = kv.val.via.map.ptr[j];
                            if (pkv.key.type != msgpack::type::STR) continue;
                            std::string pkey(pkv.key.via.str.ptr, pkv.key.via.str.size);
                            if (pkey != "interfaces" ||
                                pkv.val.type != msgpack::type::ARRAY) continue;

                            for (uint32_t k = 0; k < pkv.val.via.array.size; ++k) {
                                const auto& iobj = pkv.val.via.array.ptr[k];
                                if (iobj.type != msgpack::type::MAP) continue;

                                Interface iface;
                                for (uint32_t m = 0; m < iobj.via.map.size; ++m) {
                                    const auto& ikv = iobj.via.map.ptr[m];
                                    if (ikv.key.type != msgpack::type::STR) continue;
                                    std::string ik(ikv.key.via.str.ptr, ikv.key.via.str.size);

                                    if (ik == "name" && ikv.val.type == msgpack::type::STR)
                                        iface.name = std::string(ikv.val.via.str.ptr, ikv.val.via.str.size);
                                    else if (ik == "pattern" && ikv.val.type == msgpack::type::STR)
                                        iface.pattern = interface_pattern_from_str(
                                            std::string(ikv.val.via.str.ptr, ikv.val.via.str.size));
                                    else if (ik == "event_type" && ikv.val.type == msgpack::type::STR)
                                        iface.event_type = std::string(ikv.val.via.str.ptr, ikv.val.via.str.size);
                                    else if (ik == "durability" &&
                                             (ikv.val.type == msgpack::type::POSITIVE_INTEGER ||
                                              ikv.val.type == msgpack::type::NEGATIVE_INTEGER))
                                        iface.durability = static_cast<DurabilityLevel>(
                                            static_cast<int>(ikv.val.via.u64));
                                }
                                if (iface.event_type.empty()) iface.event_type = iface.name;
                                interfaces.push_back(std::move(iface));
                            }
                        }
                    }
                }
            }

            // Build ModuleInfo and register
            ModuleInfo module_info;
            module_info.module_id = module_id;
            module_info.interfaces = std::move(interfaces);
            register_module(module_info);
            _register_count.fetch_add(1, std::memory_order_relaxed);

            // Build ACK message
            Message ack;
            ack.msg_type = MessageType::ACK;
            ack.sender = "engine";
            ack.event = "register_ack";
            ack.payload["status"] = std::string("ok");
            ack.payload["module_id"] = module_id;
            ack.payload["event_pub_port"] = _event_endpoint.port;
            ack.payload["event_sub_port"] = _event_sub_endpoint.port;
            ack.payload["job_port"] = _job_endpoint.port;
            ack.payload["heartbeat_recv_port"] = _heartbeat_recv_endpoint.port;
            auto ack_data = serialize(ack);

            // Enqueue reply: [identity, b"", ack_data]
            MultipartMsg reply;
            reply.frames.push_back(req.identity);
            reply.frames.push_back({});  // empty delimiter
            reply.frames.push_back(ack_data);
            {
                std::lock_guard lock(_reg_out_lock);
                _reg_out_queue.push(std::move(reply));
            }

            std::cerr << "[TycheEngine] Module " << family_name
                      << " registered as " << module_id << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "[TycheEngine] Registration processing error: "
                      << e.what() << std::endl;
        }
    }
}

// ── 3. Heartbeat Worker (PUB) ───────────────────────────────────────

void TycheEngine::_heartbeat_worker() {
    zmq::socket_t socket(_zmq_ctx->ctx, zmq::socket_type::pub);
    socket.set(zmq::sockopt::linger, 0);
    socket.bind(_heartbeat_endpoint.to_string());

    while (_running.load(std::memory_order_relaxed)) {
        try {
            Message hb;
            hb.msg_type = MessageType::HEARTBEAT;
            hb.sender = "engine";
            hb.event = "heartbeat";
            hb.payload["timestamp"] = _now();
            auto data = serialize(hb);

            socket.send(zmq::message_t("heartbeat", 9), zmq::send_flags::sndmore);
            socket.send(zmq::message_t(data.data(), data.size()), zmq::send_flags::none);
        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        }
        for (int i = 0; i < 10 && _running.load(std::memory_order_relaxed); ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    socket.close();
}

// ── 4. Heartbeat Receive Worker (ROUTER) ────────────────────────────

void TycheEngine::_heartbeat_receive_worker() {
    zmq::socket_t socket(_zmq_ctx->ctx, zmq::socket_type::router);
    socket.set(zmq::sockopt::linger, 0);
    socket.set(zmq::sockopt::rcvtimeo, 100);
    socket.bind(_heartbeat_recv_endpoint.to_string());

    while (_running.load(std::memory_order_relaxed)) {
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(socket, std::back_inserter(frames));
            if (!result.has_value() || frames.size() < 2) continue;

            // [identity, msg] or [identity, b"", msg]
            const auto& msg_f = (frames.size() > 2 && frames[1].size() == 0)
                                    ? frames[2] : frames[1];
            auto msg = deserialize(msg_f.data(), msg_f.size());

            if (msg.msg_type != MessageType::HEARTBEAT) continue;

            _heartbeat_manager.update(msg.sender);

            // Extract availability map from heartbeat payload
            auto avail_it = msg.payload.find("availability");
            if (avail_it != msg.payload.end()) {
                try {
                    const auto& amap = std::any_cast<const Payload&>(avail_it->second);
                    std::unordered_map<std::string, bool> avail;
                    for (const auto& [k, v] : amap)
                        avail[k] = std::any_cast<bool>(v);
                    std::unique_lock lock(_modules_lock);
                    _module_availability[msg.sender] = std::move(avail);
                } catch (...) {}
            }

            // Recovery: if handler was marked unavailable, restore it
            {
                std::unique_lock lock(_modules_lock);
                auto uit = _unavailable_handlers.find(msg.sender);
                if (uit != _unavailable_handlers.end() && !uit->second.empty()) {
                    std::vector<std::string> topics(uit->second.begin(), uit->second.end());
                    _unavailable_handlers.erase(uit);
                    lock.unlock();

                    std::lock_guard rlock(_recovery_events_lock);
                    _recovery_events.push({msg.sender, std::move(topics)});
                }
            }
        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        } catch (...) {}
    }
    socket.close();
}

// ── 9. Job Router Worker ────────────────────────────────────────────

void TycheEngine::_job_router_worker() {
    zmq::socket_t socket(_zmq_ctx->ctx, zmq::socket_type::router);
    socket.set(zmq::sockopt::linger, 0);
    socket.set(zmq::sockopt::rcvtimeo, 50);
    socket.bind(_job_endpoint.to_string());
    std::cerr << "[TycheEngine] Job router bound to "
              << _job_endpoint.to_string() << std::endl;

    auto send_job = [&](const std::vector<std::vector<uint8_t>>& f) {
        zmq_send_frames(socket, f);
    };

    // retry_job — declared first so other lambdas can reference it
    std::function<bool(const std::string&, JobTrackingInfo&)> retry_job =
        [&](const std::string& corr_id, JobTrackingInfo& info) -> bool {
        std::vector<std::string> available;
        // OPT-3: resolve topic string to InternId once for fast lookup
        InternId topic_id = _intern.intern(info.topic);
        {
            std::shared_lock lock(_modules_lock);
            auto hit = _job_handlers.find(topic_id);
            if (hit != _job_handlers.end())
                for (const auto& h : hit->second)
                    if (_is_handler_available(h, info.topic)) available.push_back(h);
        }
        if (available.empty()) return false;
        size_t idx;
        {
            std::lock_guard l(_job_lock);
            idx = _job_round_robin[topic_id] % available.size();
            _job_round_robin[topic_id] = idx + 1;
        }
        std::string hid = available[idx];
        send_job({str_to_bytes(hid), {}, info.topic_frame, info.message_frame});
        info.handler_id = hid;
        info.dispatch_time = _now();
        { std::lock_guard l(_job_lock); _job_tracking[corr_id] = info; }
        return true;
    };

    // handle_request
    auto handle_request = [&](const std::vector<uint8_t>& identity,
                              const std::vector<uint8_t>& topic_frame,
                              const std::vector<uint8_t>& message_frame,
                              const Message& msg) {
        const std::string& topic = msg.event;
        double now = _now();
        float wt = 30.0f, rt = 60.0f;
        if (msg.wait_timeout.has_value()) wt = *msg.wait_timeout;
        else {
            auto i = msg.payload.find("wait_timeout");
            if (i != msg.payload.end()) {
                try { wt = static_cast<float>(std::any_cast<double>(i->second)); }
                catch (...) {
                    try { wt = static_cast<float>(std::any_cast<int>(i->second)); } catch (...) {}
                }
            }
        }
        if (msg.run_timeout.has_value()) rt = *msg.run_timeout;
        else {
            auto i = msg.payload.find("run_timeout");
            if (i != msg.payload.end()) {
                try { rt = static_cast<float>(std::any_cast<double>(i->second)); }
                catch (...) {
                    try { rt = static_cast<float>(std::any_cast<int>(i->second)); } catch (...) {}
                }
            }
        }

        std::vector<std::string> handlers, available;
        // OPT-3: resolve topic string to InternId once for fast lookup
        InternId topic_id = _intern.intern(topic);
        {
            std::shared_lock l(_modules_lock);
            auto h = _job_handlers.find(topic_id);
            if (h != _job_handlers.end()) handlers = h->second;
            for (const auto& hh : handlers)
                if (_is_handler_available(hh, topic)) available.push_back(hh);
        }
        std::string corr_id = msg.correlation_id.value_or("");

        if (available.empty()) {
            if (handlers.empty()) {
                Message err;
                err.msg_type = MessageType::RESPONSE;
                err.sender = "engine";
                err.event = msg.event;
                err.payload["error"] = std::string("No handler registered for job '" + topic + "'");
                err.correlation_id = msg.correlation_id;
                send_job({identity, {}, topic_frame, serialize(err)});
                return;
            }
            // All handlers unavailable — queue and wait
            JobTrackingInfo ti;
            ti.requester_id = identity;
            ti.topic = topic;
            ti.wait_start_time = now;
            ti.wait_timeout = wt;
            ti.run_timeout = rt;
            ti.topic_frame = topic_frame;
            ti.message_frame = message_frame;
            {
                std::lock_guard l(_job_lock);
                _job_tracking[corr_id] = std::move(ti);
                _pending_jobs[corr_id] = identity;
            }
            return;
        }

        // Round-robin selection
        size_t idx;
        {
            std::lock_guard l(_job_lock);
            idx = _job_round_robin[topic_id] % available.size();
            _job_round_robin[topic_id] = idx + 1;
        }
        std::string handler_id = available[idx];

        // Track the job
        {
            std::lock_guard l(_job_lock);
            _pending_jobs[corr_id] = identity;
            JobTrackingInfo ti;
            ti.requester_id = identity;
            ti.handler_id = handler_id;
            ti.topic = topic;
            ti.dispatch_time = now;
            ti.wait_start_time = now;
            ti.wait_timeout = wt;
            ti.run_timeout = rt;
            ti.topic_frame = topic_frame;
            ti.message_frame = message_frame;
            _job_tracking[corr_id] = std::move(ti);
        }

        // Forward to handler: [handler_identity, b"", topic, message]
        send_job({str_to_bytes(handler_id), {}, topic_frame, message_frame});
    };

    // handle_response
    auto handle_response = [&](const std::vector<uint8_t>&,
                               const std::vector<uint8_t>& topic_frame,
                               const std::vector<uint8_t>& message_frame,
                               const Message& msg) {
        std::string corr_id = msg.correlation_id.value_or("");
        std::vector<uint8_t> req_id;
        {
            std::lock_guard l(_job_lock);
            auto i = _pending_jobs.find(corr_id);
            if (i == _pending_jobs.end()) return;
            req_id = i->second;
            _pending_jobs.erase(i);
            _job_tracking.erase(corr_id);
        }
        send_job({req_id, {}, topic_frame, message_frame});
    };

    // process_timeout
    auto process_timeout = [&](const std::string& corr_id, const std::string& reason) {
        JobTrackingInfo info;
        {
            std::lock_guard l(_job_lock);
            auto i = _job_tracking.find(corr_id);
            if (i == _job_tracking.end()) return;
            info = std::move(i->second);
            _job_tracking.erase(i);
        }
        if (reason == "run_timeout" && !info.handler_id.empty()) {
            {
                std::unique_lock l(_modules_lock);
                _unavailable_handlers[info.handler_id].insert(info.topic);
            }
            std::cerr << "[TycheEngine] Handler '" << info.handler_id
                      << "' timed out for '" << info.topic << "'" << std::endl;
            if (retry_job(corr_id, info)) return;
            // No alternative — put back as waiting
            info.handler_id.clear();
            info.dispatch_time = 0.0;
            { std::lock_guard l(_job_lock); _job_tracking[corr_id] = info; }
            return;
        }
        if (reason == "wait_timeout") {
            try {
                auto m = deserialize(info.message_frame.data(), info.message_frame.size());
                _dead_letter_store.persist(m, info.topic, "wait_timeout");
            } catch (...) {}
            std::cerr << "[TycheEngine] Job " << corr_id
                      << " wait_timeout for '" << info.topic << "'" << std::endl;
        }
        { std::lock_guard l(_job_lock); _pending_jobs.erase(corr_id); }

        Message err;
        err.msg_type = MessageType::RESPONSE;
        err.sender = "engine";
        err.event = info.topic;
        err.payload["error"] = std::string(reason);
        err.payload["correlation_id"] = corr_id;
        err.correlation_id = corr_id;
        send_job({info.requester_id, {}, info.topic_frame, serialize(err)});
    };

    // process_recovery
    auto process_recovery = [&](const RecoveryEvent& ev) {
        std::vector<std::pair<std::string, JobTrackingInfo>> waiting;
        {
            std::lock_guard l(_job_lock);
            for (auto& [c, i] : _job_tracking) {
                if (!i.handler_id.empty()) continue;
                for (const auto& t : ev.recovered_topics)
                    if (i.topic == t) { waiting.emplace_back(c, i); break; }
            }
        }
        for (auto& [c, i] : waiting) {
            { std::lock_guard l(_job_lock); _job_tracking.erase(c); }
            if (!retry_job(c, i)) {
                std::lock_guard l(_job_lock);
                _job_tracking[c] = i;
            }
        }
        std::cerr << "[TycheEngine] Handler '" << ev.module_id
                  << "' recovered, dispatched " << waiting.size()
                  << " waiting jobs" << std::endl;
    };

    // ═══ Main loop ═══
    while (_running.load(std::memory_order_relaxed)) {
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(socket, std::back_inserter(frames));
            if (result.has_value() && frames.size() >= 4) {
                auto identity = to_bytes(frames[0]);
                auto topic_frame = to_bytes(frames[2]);
                auto message_frame = to_bytes(frames[3]);
                try {
                    auto msg = deserialize(message_frame.data(), message_frame.size());
                    if (msg.msg_type == MessageType::REQUEST)
                        handle_request(identity, topic_frame, message_frame, msg);
                    else if (msg.msg_type == MessageType::RESPONSE)
                        handle_response(identity, topic_frame, message_frame, msg);
                } catch (...) {}
            }
        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        }

        // Process timeout events — drain queue first to avoid deadlock
        {
            std::vector<JobTimeoutEvent> timeout_batch;
            {
                std::lock_guard l(_job_timeout_events_lock);
                while (!_job_timeout_events.empty()) {
                    timeout_batch.push_back(std::move(_job_timeout_events.front()));
                    _job_timeout_events.pop();
                }
            }
            for (const auto& ev : timeout_batch)
                process_timeout(ev.correlation_id, ev.reason);
        }

        // Process recovery events — drain queue first to avoid deadlock
        {
            std::vector<RecoveryEvent> recovery_batch;
            {
                std::lock_guard l(_recovery_events_lock);
                while (!_recovery_events.empty()) {
                    recovery_batch.push_back(std::move(_recovery_events.front()));
                    _recovery_events.pop();
                }
            }
            for (const auto& ev : recovery_batch)
                process_recovery(ev);
        }
    }
    socket.close();
}

// ── 10. Job Timeout Worker ──────────────────────────────────────────

void TycheEngine::_job_timeout_worker() {
    while (_running.load(std::memory_order_relaxed)) {
        double now = _now();
        std::vector<JobTimeoutEvent> events;
        {
            std::lock_guard lock(_job_lock);
            for (const auto& [cid, info] : _job_tracking) {
                bool timed_out = false;
                std::string reason;
                if (!info.handler_id.empty()) {
                    if (now - info.dispatch_time > static_cast<double>(info.run_timeout)) {
                        timed_out = true;
                        reason = "run_timeout";
                    }
                } else {
                    if (now - info.wait_start_time > static_cast<double>(info.wait_timeout)) {
                        timed_out = true;
                        reason = "wait_timeout";
                    }
                }
                if (timed_out)
                    events.push_back({cid, std::move(reason)});
            }
        }
        // Push events after releasing _job_lock to avoid deadlock
        if (!events.empty()) {
            std::lock_guard tl(_job_timeout_events_lock);
            for (auto& ev : events)
                _job_timeout_events.push(std::move(ev));
        }
        for (int i = 0; i < 10 && _running.load(std::memory_order_relaxed); ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

// ── 5. Monitor Worker ───────────────────────────────────────────────

void TycheEngine::_monitor_worker() {
    while (_running.load(std::memory_order_relaxed)) {
        auto expired = _heartbeat_manager.tick_all();
        for (const auto& mid : expired) {
            std::cerr << "[TycheEngine] Module " << mid << " expired" << std::endl;
            unregister_module(mid);
        }

        // Topic queue GC — snapshot activity under _modules_lock first,
        // then GC using sharded map per-bucket locks (OPT-2).
        // _topic_subscribers / _topic_producers use InternId keys; we resolve
        // them to strings via _intern for comparison with ShardedTopicQueueMap.
        double now = _now();
        std::unordered_set<std::string> active_topics;
        {
            std::shared_lock mlock(_modules_lock);
            for (const auto& [topic_id, subs] : _topic_subscribers)
                if (!subs.empty()) active_topics.insert(std::string(_intern.resolve(topic_id)));
            for (const auto& [topic_id, prods] : _topic_producers)
                if (!prods.empty()) active_topics.insert(std::string(_intern.resolve(topic_id)));
        }
        {
            auto queues = _topic_queues.snapshot();
            for (const auto& [topic, q] : queues) {
                if (active_topics.count(topic)) continue;
                double last = _topic_queues.last_access(topic);
                if (last == 0.0) last = now;
                if (now - last > _topic_queue_ttl) {
                    _topic_queues.erase(topic);
                }
            }
        }

        for (int i = 0; i < 10 && _running.load(std::memory_order_relaxed); ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

// ── 6. Event Proxy Worker (XPUB/XSUB) ──────────────────────────────

void TycheEngine::_event_proxy_worker() {
    zmq::socket_t xpub(_zmq_ctx->ctx, zmq::socket_type::xpub);
    xpub.set(zmq::sockopt::linger, 0);
    xpub.set(zmq::sockopt::sndhwm, 10000);
    xpub.set(zmq::sockopt::rcvhwm, 10000);

    zmq::socket_t xsub(_zmq_ctx->ctx, zmq::socket_type::xsub);
    xsub.set(zmq::sockopt::linger, 0);
    xsub.set(zmq::sockopt::sndhwm, 10000);
    xsub.set(zmq::sockopt::rcvhwm, 10000);

    xpub.bind(_event_endpoint.to_string());
    xsub.bind(_event_sub_endpoint.to_string());

    // Pre-subscribe XSUB to all topics — solves ZMQ slow-joiner problem
    uint8_t sub_all = 0x01;
    xsub.send(zmq::message_t(&sub_all, 1), zmq::send_flags::none);

    zmq_pollitem_t items[] = {
        {static_cast<void*>(xpub), 0, ZMQ_POLLIN, 0},
        {static_cast<void*>(xsub), 0, ZMQ_POLLIN, 0},
    };

    while (_running.load(std::memory_order_relaxed)) {
        try {
            zmq::poll(items, 2, std::chrono::milliseconds(100));
        } catch (const zmq::error_t&) { break; }

        // XPUB → XSUB: forward subscription/unsubscription messages
        if (items[0].revents & ZMQ_POLLIN) {
            std::vector<zmq::message_t> frames;
            zmq::recv_multipart(xpub, std::back_inserter(frames));
            for (size_t i = 0; i < frames.size(); ++i) {
                auto f = (i + 1 < frames.size()) ? zmq::send_flags::sndmore
                                                  : zmq::send_flags::none;
                xsub.send(zmq::message_t(frames[i].data(), frames[i].size()), f);
            }
        }

        // XSUB → XPUB: forward events + enqueue to topic queues
        if (items[1].revents & ZMQ_POLLIN) {
            int batch = 0;
            while (_running.load(std::memory_order_relaxed)) {
                std::vector<zmq::message_t> frames;
                try {
                    auto r = zmq::recv_multipart(xsub, std::back_inserter(frames),
                                                 zmq::recv_flags::dontwait);
                    if (!r.has_value() || frames.empty()) break;
                } catch (...) { break; }

                // Hot path: direct forward to XPUB
                try {
                    for (size_t i = 0; i < frames.size(); ++i) {
                        auto f = (i + 1 < frames.size()) ? zmq::send_flags::sndmore
                                                          : zmq::send_flags::none;
                        xpub.send(zmq::message_t(frames[i].data(), frames[i].size()), f);
                    }
                } catch (...) {}

                // Cold path: enqueue for monitoring / dead-letter
                // OPT-1: Pass zmq::message_t frames directly to avoid to_bytes()
                // allocation. _enqueue_from_xsub converts to SSO-optimized Frame.
                std::vector<std::vector<uint8_t>> bframes;
                bframes.reserve(frames.size());
                for (const auto& f : frames) {
                    bframes.emplace_back(
                        static_cast<const uint8_t*>(f.data()),
                        static_cast<const uint8_t*>(f.data()) + f.size());
                }
                _enqueue_from_xsub(bframes);
                ++batch;
            }
            if (batch > 0)
                _event_count.fetch_add(static_cast<uint64_t>(batch), std::memory_order_relaxed);
        }
    }
    xpub.close();
    xsub.close();
}

// ── 7. Event Egress Worker ──────────────────────────────────────────

void TycheEngine::_event_egress_worker() {
    while (_running.load(std::memory_order_relaxed)) {
        {
            std::unique_lock lock(_egress_wakeup_lock);
            _egress_wakeup_cv.wait_for(lock, std::chrono::seconds(1),
                [this]() { return _egress_wakeup_flag || !_running.load(); });
            _egress_wakeup_flag = false;
        }
        if (!_running.load()) break;

        // Snapshot topic queues — hold shared_ptr to prevent use-after-free
        // OPT-2: sharded map snapshot acquires each bucket lock sequentially.
        auto queues = _topic_queues.snapshot();

        for (auto& [topic, q] : queues) {
            while (_running.load(std::memory_order_relaxed)) {
                auto item = q->get();
                if (!item.has_value()) break;

                double now = _now();
                if (now - item->enqueue_time > _broadcast_ttl) {
                    try {
                        const auto& fr = item->frames;
                        const auto& md = (fr.size() >= 2) ? fr[1] : fr[0];
                        auto m = deserialize(md.data(), md.size());
                        _dead_letter_store.persist(m, topic, "broadcast_ttl_expired");
                    } catch (...) {}
                }

                _topic_queues.touch(topic, _now());
            }
        }
    }
}

// ── 8. Admin Worker ─────────────────────────────────────────────────

void TycheEngine::_admin_worker() {
    zmq::socket_t socket(_zmq_ctx->ctx, zmq::socket_type::router);
    socket.set(zmq::sockopt::linger, 0);
    socket.set(zmq::sockopt::rcvtimeo, 100);
    socket.bind(_admin_endpoint.to_string());

    while (_running.load(std::memory_order_relaxed)) {
        try {
            std::vector<zmq::message_t> frames;
            auto result = zmq::recv_multipart(socket, std::back_inserter(frames));
            if (!result.has_value() || frames.size() < 2) continue;

            auto identity = to_bytes(frames[0]);
            const auto& msg_f = (frames.size() >= 3 && frames[1].size() == 0)
                                    ? frames[2] : frames[1];

            msgpack::object_handle oh = msgpack::unpack(
                static_cast<const char*>(msg_f.data()), msg_f.size());
            const auto& qobj = oh.get();

            std::string query;
            if (qobj.type == msgpack::type::STR)
                query = std::string(qobj.via.str.ptr, qobj.via.str.size);

            msgpack::sbuffer rbuf;
            msgpack::packer<msgpack::sbuffer> pk(&rbuf);

            if (query == "STATUS") {
                pk.pack_map(4);
                pk.pack(std::string("status")); pk.pack(std::string("running"));
                pk.pack(std::string("uptime")); pk.pack(_now() - _start_time);
                pk.pack(std::string("module_count"));
                { std::shared_lock l(_modules_lock); pk.pack(static_cast<int>(_modules.size())); }
                pk.pack(std::string("event_count")); pk.pack(_event_count.load());
            } else if (query == "MODULES") {
                std::shared_lock l(_modules_lock);
                pk.pack_map(1); pk.pack(std::string("modules"));
                pk.pack_array(static_cast<uint32_t>(_modules.size()));
                for (const auto& [mid, info] : _modules) {
                    pk.pack_map(4);
                    pk.pack(std::string("module_id")); pk.pack(mid);
                    pk.pack(std::string("liveness")); pk.pack(_heartbeat_manager.get_liveness(mid));
                    pk.pack(std::string("interfaces"));
                    pk.pack_array(static_cast<uint32_t>(info.interfaces.size()));
                    for (const auto& i : info.interfaces) pk.pack(i.name);
                    pk.pack(std::string("availability"));
                    auto ait = _module_availability.find(mid);
                    if (ait != _module_availability.end()) {
                        pk.pack_map(static_cast<uint32_t>(ait->second.size()));
                        for (const auto& [k, v] : ait->second) { pk.pack(k); pk.pack(v); }
                    } else { pk.pack_map(0); }
                }
            } else if (query == "QUEUES") {
                auto queues = _topic_queues.snapshot();
                pk.pack_map(1); pk.pack(std::string("queues"));
                pk.pack_array(static_cast<uint32_t>(queues.size()));
                for (const auto& [t, q] : queues) {
                    pk.pack_map(5);
                    pk.pack(std::string("name")); pk.pack(t);
                    pk.pack(std::string("size")); pk.pack(static_cast<uint64_t>(q->size()));
                    pk.pack(std::string("capacity")); pk.pack(static_cast<uint64_t>(q->capacity()));
                    pk.pack(std::string("processed")); pk.pack(q->processed());
                    pk.pack(std::string("dropped")); pk.pack(q->dropped());
                }
            } else if (query == "JOBS") {
                std::lock_guard l(_job_lock);
                pk.pack_map(1); pk.pack(std::string("jobs"));
                pk.pack_array(static_cast<uint32_t>(_job_tracking.size()));
                for (const auto& [cid, info] : _job_tracking) {
                    pk.pack_map(5);
                    pk.pack(std::string("correlation_id")); pk.pack(cid);
                    pk.pack(std::string("topic")); pk.pack(info.topic);
                    pk.pack(std::string("handler_id")); pk.pack(info.handler_id);
                    pk.pack(std::string("wait_timeout")); pk.pack(static_cast<double>(info.wait_timeout));
                    pk.pack(std::string("run_timeout")); pk.pack(static_cast<double>(info.run_timeout));
                }
            } else if (query == "DEAD_LETTERS") {
                auto records = _dead_letter_store.replay();
                pk.pack_map(1); pk.pack(std::string("dead_letters"));
                pk.pack_array(static_cast<uint32_t>(records.size()));
                for (const auto& r : records) pk.pack(r);
            } else if (query == "STATS") {
                pk.pack_map(3);
                pk.pack(std::string("event_count")); pk.pack(_event_count.load());
                pk.pack(std::string("register_count")); pk.pack(_register_count.load());
                pk.pack(std::string("module_count"));
                { std::shared_lock l(_modules_lock); pk.pack(static_cast<int>(_modules.size())); }
            } else {
                pk.pack_map(1);
                pk.pack(std::string("error"));
                pk.pack(std::string("Unknown query: ") + query);
            }

            // Send: [identity, b"", response]
            zmq_send_frames(socket, {
                identity, {},
                {reinterpret_cast<const uint8_t*>(rbuf.data()),
                 reinterpret_cast<const uint8_t*>(rbuf.data()) + rbuf.size()}
            });

        } catch (const zmq::error_t& e) {
            if (e.num() == ETERM) break;
        } catch (...) {}
    }
    socket.close();
}

}  // namespace tyche
