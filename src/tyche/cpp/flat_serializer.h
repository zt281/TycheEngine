#pragma once

// FlatMessage serializer -- zero-copy binary serialization for C++ module interop.
//
// Provides serialize_flat() / deserialize_flat() for Message <-> FlatMessageHeader
// conversion without heap allocation on the hot path.
//
// NOTE: This format is for C++ module-to-module communication only.
// Cross-language communication (C++ <-> Python) still uses msgpack.

#include "tyche/cpp/flat_message.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace tyche {

// ── serialize_flat ──────────────────────────────────────────────────
//
// Serialize Message into caller-provided buffer. Returns bytes written, or 0 on overflow.
// All operations are noexcept; no heap allocation.
inline size_t serialize_flat(const Message& msg, uint8_t* buffer, size_t capacity) noexcept {
    if (!buffer || capacity < sizeof(FlatMessageHeader)) return 0;

    const size_t sender_len = msg.sender.size();
    const size_t event_len = msg.event.size();

    // Calculate payload size: simplified msgpack-like encoding
    // Format: [uint32_t map_size] [key1_len][key1][type1][value1] ...
    size_t payload_len = 0;
    if (!msg.payload.empty()) {
        payload_len += 4;  // map size (uint32_t)
        for (const auto& [k, v] : msg.payload) {
            payload_len += 4 + k.size();  // key_len (uint32_t) + key bytes
            payload_len += 1;  // type marker
            if (v.type() == typeid(std::string)) {
                const auto& s = std::any_cast<const std::string&>(v);
                payload_len += 4 + s.size();  // str_len (uint32_t) + str bytes
            } else if (v.type() == typeid(double)) {
                payload_len += 8;  // double
            } else if (v.type() == typeid(int)) {
                payload_len += 4;  // int32_t
            } else if (v.type() == typeid(int64_t)) {
                payload_len += 8;  // int64_t
            } else if (v.type() == typeid(uint64_t)) {
                payload_len += 8;  // uint64_t
            } else if (v.type() == typeid(float)) {
                payload_len += 4;  // float
            } else if (v.type() == typeid(bool)) {
                payload_len += 1;  // bool
            } else {
                payload_len += 0;  // nil / unsupported
            }
        }
    }

    const size_t total_size = sizeof(FlatMessageHeader) + sender_len + event_len + payload_len;
    if (total_size > capacity) return 0;

    FlatMessageHeader* hdr = reinterpret_cast<FlatMessageHeader*>(buffer);
    hdr->msg_type = static_cast<uint8_t>(msg.msg_type);
    hdr->durability = static_cast<uint8_t>(msg.durability);
    hdr->sender_len = static_cast<uint16_t>(sender_len);
    hdr->event_len = static_cast<uint16_t>(event_len);
    hdr->payload_len = static_cast<uint16_t>(payload_len > 65535 ? 65535 : payload_len);
    hdr->total_size = static_cast<uint32_t>(total_size);
    hdr->timestamp = msg.timestamp.value_or(0.0);

    uint8_t* p = buffer + sizeof(FlatMessageHeader);

    // Write sender
    if (sender_len > 0) {
        std::memcpy(p, msg.sender.data(), sender_len);
        p += sender_len;
    }

    // Write event
    if (event_len > 0) {
        std::memcpy(p, msg.event.data(), event_len);
        p += event_len;
    }

    // Write payload
    if (!msg.payload.empty()) {
        // Map size
        uint32_t map_size = static_cast<uint32_t>(msg.payload.size());
        std::memcpy(p, &map_size, 4);
        p += 4;

        for (const auto& [k, v] : msg.payload) {
            // Key length + key
            uint32_t key_len = static_cast<uint32_t>(k.size());
            std::memcpy(p, &key_len, 4);
            p += 4;
            std::memcpy(p, k.data(), k.size());
            p += k.size();

            // Type marker + value
            if (v.type() == typeid(std::string)) {
                *p++ = 0x01;  // string marker
                const auto& s = std::any_cast<const std::string&>(v);
                uint32_t str_len = static_cast<uint32_t>(s.size());
                std::memcpy(p, &str_len, 4);
                p += 4;
                std::memcpy(p, s.data(), s.size());
                p += s.size();
            } else if (v.type() == typeid(double)) {
                *p++ = 0x02;  // double marker
                double d = std::any_cast<double>(v);
                std::memcpy(p, &d, 8);
                p += 8;
            } else if (v.type() == typeid(int)) {
                *p++ = 0x03;  // int marker
                int i = std::any_cast<int>(v);
                std::memcpy(p, &i, 4);
                p += 4;
            } else if (v.type() == typeid(int64_t)) {
                *p++ = 0x04;  // int64 marker
                int64_t i64 = std::any_cast<int64_t>(v);
                std::memcpy(p, &i64, 8);
                p += 8;
            } else if (v.type() == typeid(uint64_t)) {
                *p++ = 0x05;  // uint64 marker
                uint64_t u64 = std::any_cast<uint64_t>(v);
                std::memcpy(p, &u64, 8);
                p += 8;
            } else if (v.type() == typeid(float)) {
                *p++ = 0x06;  // float marker
                float f = std::any_cast<float>(v);
                std::memcpy(p, &f, 4);
                p += 4;
            } else if (v.type() == typeid(bool)) {
                *p++ = 0x07;  // bool marker
                bool b = std::any_cast<bool>(v);
                *p++ = b ? 1 : 0;
            } else {
                *p++ = 0x00;  // nil marker
            }
        }
    }

    return total_size;
}

// ── deserialize_flat ────────────────────────────────────────────────
//
// Deserialize FlatMessage bytes into Message. Payload stored as raw bytes in msg.payload["__flat__"].
// Returns Message with msg_type=COMMAND on error (empty input or invalid header).
inline Message deserialize_flat(const uint8_t* data, size_t size) noexcept {
    Message msg;
    if (!data || size < sizeof(FlatMessageHeader)) {
        msg.msg_type = MessageType::COMMAND;  // error marker
        return msg;
    }

    const FlatMessageHeader* hdr = reinterpret_cast<const FlatMessageHeader*>(data);
    if (hdr->total_size > size) {
        msg.msg_type = MessageType::COMMAND;  // error marker
        return msg;
    }

    msg.msg_type = static_cast<MessageType>(hdr->msg_type);
    msg.durability = static_cast<DurabilityLevel>(hdr->durability);
    msg.timestamp = hdr->timestamp;

    const uint8_t* p = data + sizeof(FlatMessageHeader);
    const uint8_t* end = data + size;

    // Read sender
    if (hdr->sender_len > 0 && p + hdr->sender_len <= end) {
        msg.sender = std::string(reinterpret_cast<const char*>(p), hdr->sender_len);
        p += hdr->sender_len;
    }

    // Read event
    if (hdr->event_len > 0 && p + hdr->event_len <= end) {
        msg.event = std::string(reinterpret_cast<const char*>(p), hdr->event_len);
        p += hdr->event_len;
    }

    // Read payload: store raw bytes for later processing
    size_t payload_remaining = end - p;
    if (payload_remaining > 0 && hdr->payload_len > 0) {
        size_t payload_bytes = std::min(static_cast<size_t>(hdr->payload_len), payload_remaining);
        std::vector<uint8_t> raw_payload(p, p + payload_bytes);
        msg.payload["__flat__"] = std::move(raw_payload);
    }

    return msg;
}

// ── serialize_flat_quote ────────────────────────────────────────────
//
// Serialize a FlatQuoteTick directly into a ZMQ-compatible frame buffer.
// Returns bytes written (always sizeof(FlatQuoteTickData) on success, 0 on misalignment).
inline size_t serialize_flat_quote(const FlatQuoteTick& tick, uint8_t* buffer, size_t capacity) noexcept {
    if (!buffer || capacity < sizeof(FlatQuoteTickData)) return 0;
    if (reinterpret_cast<uintptr_t>(buffer) % alignof(FlatQuoteTickData) != 0) return 0;
    std::memcpy(buffer, &tick.data, sizeof(FlatQuoteTickData));
    return sizeof(FlatQuoteTickData);
}

// ── deserialize_flat_quote ──────────────────────────────────────────
//
// Deserialize FlatQuoteTick from raw bytes (zero-copy pointer cast).
// Returns nullptr if size < sizeof(FlatQuoteTickData) or alignment is wrong.
inline const FlatQuoteTick* deserialize_flat_quote(const uint8_t* data, size_t size) noexcept {
    if (!data || size < sizeof(FlatQuoteTickData)) return nullptr;
    if (reinterpret_cast<uintptr_t>(data) % alignof(FlatQuoteTickData) != 0) return nullptr;
    return reinterpret_cast<const FlatQuoteTick*>(data);
}

} // namespace tyche
