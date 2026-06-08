// Shared message serialization implementation for Tyche Engine.
//
// Extracted from module.cpp anonymous namespace to allow reuse by both
// TycheModule (C++ modules) and the Engine core.

#include "tyche/cpp/message.h"

#include <cstdint>
#include <string>
#include <vector>

namespace tyche {

// ── pack_any ─────────────────────────────────────────────────────────

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
    } else if (value.type() == typeid(std::vector<std::any>)) {
        const auto& vec = std::any_cast<const std::vector<std::any>&>(value);
        pk.pack_array(static_cast<uint32_t>(vec.size()));
        for (const auto& item : vec) {
            pack_any(pk, item);
        }
    } else {
        // Unknown type -- pack as nil
        pk.pack_nil();
    }
}

// ── unpack_object ────────────────────────────────────────────────────

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
            // Check if all elements are strings (non-empty) for backward compat
            bool all_str = (obj.via.array.size > 0);
            for (uint32_t i = 0; i < obj.via.array.size; ++i) {
                if (obj.via.array.ptr[i].type != msgpack::type::STR) {
                    all_str = false;
                    break;
                }
            }
            if (all_str) {
                std::vector<std::string> arr;
                arr.reserve(obj.via.array.size);
                for (uint32_t i = 0; i < obj.via.array.size; ++i) {
                    const auto& elem = obj.via.array.ptr[i];
                    arr.emplace_back(elem.via.str.ptr, elem.via.str.size);
                }
                return std::any{std::move(arr)};
            } else {
                std::vector<std::any> arr;
                arr.reserve(obj.via.array.size);
                for (uint32_t i = 0; i < obj.via.array.size; ++i) {
                    arr.push_back(unpack_object(obj.via.array.ptr[i]));
                }
                return std::any{std::move(arr)};
            }
        }
        default:
            return std::any{};
    }
}

// ── serialize ────────────────────────────────────────────────────────

std::vector<uint8_t> serialize(const Message& msg) {
    msgpack::sbuffer buffer;
    msgpack::packer<msgpack::sbuffer> pk(&buffer);

    // 10 fields: msg_type, sender, event, payload, recipient,
    //            durability, timestamp, correlation_id, wait_timeout, run_timeout
    pk.pack_map(10);

    pk.pack(std::string("msg_type"));
    pk.pack(std::string(message_type_to_str(msg.msg_type)));

    pk.pack(std::string("sender"));
    pk.pack(msg.sender);

    pk.pack(std::string("event"));
    pk.pack(msg.event);

    pk.pack(std::string("payload"));
    pk.pack_map(static_cast<uint32_t>(msg.payload.size()));
    for (const auto& [k, v] : msg.payload) {
        pk.pack(k);
        pack_any(pk, v);
    }

    pk.pack(std::string("recipient"));
    if (msg.recipient.has_value()) {
        pk.pack(*msg.recipient);
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("durability"));
    pk.pack(static_cast<int>(msg.durability));

    pk.pack(std::string("timestamp"));
    if (msg.timestamp.has_value()) {
        pk.pack(*msg.timestamp);
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("correlation_id"));
    if (msg.correlation_id.has_value()) {
        pk.pack(*msg.correlation_id);
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("wait_timeout"));
    if (msg.wait_timeout.has_value()) {
        pk.pack(static_cast<double>(*msg.wait_timeout));
    } else {
        pk.pack_nil();
    }

    pk.pack(std::string("run_timeout"));
    if (msg.run_timeout.has_value()) {
        pk.pack(static_cast<double>(*msg.run_timeout));
    } else {
        pk.pack_nil();
    }

    return std::vector<uint8_t>(buffer.data(), buffer.data() + buffer.size());
}

// ── deserialize ──────────────────────────────────────────────────────

Message deserialize(const void* data, size_t size) {
    return deserialize(static_cast<const uint8_t*>(data), size);
}

Message deserialize(const uint8_t* data, size_t size) {
    Message msg;
    msgpack::object_handle oh =
        msgpack::unpack(reinterpret_cast<const char*>(data), size);
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
        } else if (key == "correlation_id") {
            if (kv.val.type == msgpack::type::STR) {
                msg.correlation_id = std::string(kv.val.via.str.ptr, kv.val.via.str.size);
            }
        } else if (key == "timestamp") {
            if (kv.val.type == msgpack::type::FLOAT32 ||
                kv.val.type == msgpack::type::FLOAT64) {
                msg.timestamp = kv.val.via.f64;
            } else if (kv.val.type == msgpack::type::POSITIVE_INTEGER) {
                msg.timestamp = static_cast<double>(kv.val.via.u64);
            }
        } else if (key == "wait_timeout") {
            if (kv.val.type == msgpack::type::FLOAT32 ||
                kv.val.type == msgpack::type::FLOAT64) {
                msg.wait_timeout = static_cast<float>(kv.val.via.f64);
            } else if (kv.val.type == msgpack::type::POSITIVE_INTEGER) {
                msg.wait_timeout = static_cast<float>(kv.val.via.u64);
            }
        } else if (key == "run_timeout") {
            if (kv.val.type == msgpack::type::FLOAT32 ||
                kv.val.type == msgpack::type::FLOAT64) {
                msg.run_timeout = static_cast<float>(kv.val.via.f64);
            } else if (kv.val.type == msgpack::type::POSITIVE_INTEGER) {
                msg.run_timeout = static_cast<float>(kv.val.via.u64);
            }
        }
    }
    return msg;
}

}  // namespace tyche
