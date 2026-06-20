#pragma once

// Shared message serialization module for Tyche Engine.
//
// Provides a Message struct and serialize/deserialize functions
// compatible with Python's msgpack-based wire format.

#include <msgpack.hpp>

#include <any>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "tyche/cpp/types.h"

namespace tyche {

// Message structure - corresponds to Python Message dataclass.
struct Message {
    MessageType msg_type = MessageType::EVENT;
    std::string sender;
    std::string event;
    Payload payload;
    std::optional<std::string> recipient;
    DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH;
    std::optional<double> timestamp;
    std::optional<std::string> correlation_id;
    std::optional<float> wait_timeout;  // Job wait timeout
    std::optional<float> run_timeout;   // Job run timeout
};

// ── Serialization / Deserialization public API ───────────────────────

// Serialize a Message into a msgpack byte vector.
// Output is binary-compatible with Python msgpack.packb(data, use_bin_type=True).
std::vector<uint8_t> serialize(const Message& msg);

// Deserialize a msgpack byte buffer into a Message.
Message deserialize(const uint8_t* data, size_t size);
Message deserialize(const void* data, size_t size);

// ── TLS Buffer Serialization (zero-allocation hot path) ────────────

// Buffer view referencing thread-local storage. Valid only until next serialize_tls call.
struct BufferView {
    const uint8_t* data;
    size_t size;
};

// Serialize into thread-local buffer. Zero heap allocation. Not thread-safe across calls.
// The returned BufferView is valid only until the next call to serialize_tls on this thread.
BufferView serialize_tls(const Message& msg) noexcept;

// Serialize into caller-provided buffer. Returns bytes written, or 0 on overflow.
size_t serialize_into(const Message& msg, uint8_t* buffer, size_t capacity) noexcept;

// ── Helper functions (public, for advanced usage) ────────────────────

// Pack a std::any value into a msgpack packer.
// Supports: string, int, int64_t, uint64_t, double, float, bool,
//           nullptr/empty, nested Payload, vector<string>.
void pack_any(msgpack::packer<msgpack::sbuffer>& pk, const std::any& value);

// Convert a msgpack::object to std::any.
std::any unpack_object(const msgpack::object& obj);

}  // namespace tyche
