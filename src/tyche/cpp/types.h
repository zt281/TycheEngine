#pragma once

// Core type definitions for Tyche Engine -- mirrors src/tyche/types.py.
//
// Header-only: contains POD-ish structs, enums, and inline ModuleId helpers.

#include <any>
#include <cstddef>
#include <random>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace tyche {

// ── Heartbeat / Paranoid Pirate Pattern constants ──────────────────

inline constexpr double HEARTBEAT_INTERVAL = 1.0;  // seconds
inline constexpr int HEARTBEAT_LIVENESS = 3;       // missed beats before "dead"

// Admin endpoint default port.
inline constexpr int ADMIN_PORT_DEFAULT = 5560;

// ── Generic JSON-like payload (Dict[str, Any] equivalent) ──────────

using Payload = std::unordered_map<std::string, std::any>;

// ── Module identifier helpers ──────────────────────────────────────

namespace ModuleId {

// Greek deity prefixes used by generate().
inline constexpr std::string_view DEITIES[] = {
    "zeus",     "hera",   "poseidon", "hades",      "example",
    "apollo",   "artemis", "ares",    "aphrodite",  "hermes",
    "dionysus", "demeter", "hephaestus", "hestia",
};

// Generate a new module ID in the format {deity}{6-char hex}.
//
// If `deity` is empty, a random one is selected from DEITIES.
inline std::string generate(std::string_view deity = "") {
    static thread_local std::mt19937 rng{std::random_device{}()};

    std::string_view prefix;
    if (deity.empty()) {
        std::uniform_int_distribution<std::size_t> pick(
            0, std::size(DEITIES) - 1);
        prefix = DEITIES[pick(rng)];
    } else {
        prefix = deity;
    }

    // 6 hex chars (3 bytes worth of randomness).
    std::uniform_int_distribution<unsigned int> hex_dist(0, 0xFFFFFFu);
    const unsigned int suffix = hex_dist(rng);

    std::ostringstream oss;
    oss << prefix;
    oss << std::hex;
    oss.fill('0');
    oss.width(6);
    oss << suffix;
    return oss.str();
}

}  // namespace ModuleId

// ── Enums (mirror src/tyche/types.py) ──────────────────────────────

enum class EventType {
    REQUEST,
    RESPONSE,
    EVENT,
    HEARTBEAT,
    REGISTER,
    ACK,
};

// Module interface naming patterns (v3).
//
// Unified model: modules either consume events (on_*) or produce
// events (send_*). Routing semantics (broadcast, P2P, stream) are
// determined by subscriber configuration, not method-name prefixes.
enum class InterfacePattern {
    ON,
    SEND,
};

enum class BackpressureStrategy {
    DROP_OLDEST,
    DROP_NEWEST,
    BLOCK_PRODUCER,
};

// Event persistence durability levels.
enum class DurabilityLevel : int {
    BEST_EFFORT = 0,   // No persistence guarantee
    ASYNC_FLUSH = 1,   // Async write (default)
    SYNC_FLUSH  = 2,   // Sync write, confirmed
};

enum class MessageType {
    COMMAND,
    EVENT,
    HEARTBEAT,
    REGISTER,
    ACK,
    RESPONSE,
};

// ── String conversion helpers ─────────────────────────────────────

// String conversion for MessageType (matches Python MessageType.value)
inline const char* message_type_to_str(MessageType t) {
    switch (t) {
        case MessageType::COMMAND:   return "cmd";
        case MessageType::EVENT:     return "evt";
        case MessageType::HEARTBEAT: return "hbt";
        case MessageType::REGISTER:  return "reg";
        case MessageType::ACK:       return "ack";
        case MessageType::RESPONSE:  return "resp";
    }
    return "evt";
}

inline MessageType message_type_from_str(const std::string& s) {
    if (s == "cmd")  return MessageType::COMMAND;
    if (s == "evt")  return MessageType::EVENT;
    if (s == "hbt")  return MessageType::HEARTBEAT;
    if (s == "reg")  return MessageType::REGISTER;
    if (s == "ack")  return MessageType::ACK;
    if (s == "resp") return MessageType::RESPONSE;
    return MessageType::EVENT;
}

// String conversion for InterfacePattern (matches Python InterfacePattern.value)
inline const char* interface_pattern_to_str(InterfacePattern p) {
    switch (p) {
        case InterfacePattern::ON:   return "on";
        case InterfacePattern::SEND: return "send";
    }
    return "on";
}

// ── Structs ────────────────────────────────────────────────────────

// Network endpoint configuration.
struct Endpoint {
    std::string host;
    int port = 0;

    Endpoint() = default;
    Endpoint(std::string h, int p) : host(std::move(h)), port(p) {}

    std::string to_string() const {
        return "tcp://" + host + ":" + std::to_string(port);
    }
};

// Module interface definition.
struct Interface {
    std::string name;
    InterfacePattern pattern = InterfacePattern::ON;
    std::string event_type;
    DurabilityLevel durability = DurabilityLevel::ASYNC_FLUSH;
    BackpressureStrategy backpressure = BackpressureStrategy::DROP_OLDEST;
    int max_queue_depth = 10000;
};

// Module registration information.
struct ModuleInfo {
    std::string module_id;
    Endpoint endpoint;
    std::vector<Interface> interfaces;
    Payload metadata;
};

}  // namespace tyche
