#pragma once

// FlatMessage -- zero-copy binary message format for C++ module interop.
//
// FlatMessageHeader (24 bytes packed) and FlatQuoteTick (72 bytes packed)
// are designed for:
//   - Zero heap allocation on hot path
//   - Cache-line aligned access (64-byte alignment)
//   - memcpy-based serialization (no msgpack overhead)
//   - Zero-copy deserialization (direct pointer cast)
//
// NOTE: This format is for C++ module-to-module communication only.
// Cross-language communication (C++ <-> Python) still uses msgpack.

#include <cstdint>
#include <cstring>

namespace tyche {

// ── FlatMessageHeader ─────────────────────────────────────────────────
//
// Packed binary header for variable-length messages.
// Layout (24 bytes):
//   uint8_t  msg_type     (1 byte)
//   uint8_t  durability  (1 byte)
//   uint16_t sender_len   (2 bytes)
//   uint16_t event_len    (2 bytes)
//   uint16_t payload_len  (2 bytes)
//   uint32_t total_size    (4 bytes)
//   double   timestamp     (8 bytes)
//   Total: 1+1+2+2+2+4+8 = 20 bytes, padded to 24 for alignment
//
// Followed by variable data:
//   [sender bytes: sender_len]
//   [event bytes: event_len]
//   [payload bytes: payload_len]
#pragma pack(push, 1)
struct FlatMessageHeader {
    uint8_t  msg_type;      // MessageType enum value
    uint8_t  durability;   // DurabilityLevel enum value
    uint16_t sender_len;    // sender string length
    uint16_t event_len;     // event string length
    uint16_t payload_len;   // payload region total length
    uint32_t total_size;   // total message bytes (including header)
    double   timestamp;     // high-precision timestamp
    uint8_t  _pad[4];      // padding to 24 bytes (20 + 4)

    // Accessors for variable data offsets
    const uint8_t* sender_data() const {
        return reinterpret_cast<const uint8_t*>(this + 1);
    }
    const uint8_t* event_data() const {
        return sender_data() + sender_len;
    }
    const uint8_t* payload_data() const {
        return event_data() + event_len;
    }
};
#pragma pack(pop)

static_assert(sizeof(FlatMessageHeader) == 24,
              "FlatMessageHeader must be 24 bytes");
static_assert(alignof(FlatMessageHeader) <= 8,
              "FlatMessageHeader alignment should not exceed 8");

// ── FlatQuoteTick ─────────────────────────────────────────────────────
//
// Fixed-layout market tick message (72 bytes packed).
// Designed for CTP option market data hot path.
//
// NOTE: alignas(64) is applied OUTSIDE the #pragma pack block because
// MSVC treats alignas as overriding pack(1), causing sizeof == 64
// instead of 72. We use a wrapper struct for cache-line alignment.
//
// Layout (72 bytes):
//   char     symbol[16]    (16 bytes) - instrument code (zero-padded)
//   double   bid           (8 bytes)
//   double   ask           (8 bytes)
//   double   last          (8 bytes)
//   int64_t  volume        (8 bytes)
//   double   timestamp     (8 bytes) - exchange timestamp
//   double   local_ts      (8 bytes) - local receive timestamp
//   uint32_t tick_count    (4 bytes) - sequence number
//   uint8_t  flags         (1 byte)  - bit0: is_option, bit1: is_stale
//   uint8_t  _pad[3]       (3 bytes) - padding to 72 bytes
//
// Total: 16+8+8+8+8+8+8+4+1+3 = 72 bytes
#pragma pack(push, 1)
struct FlatQuoteTickData {
    char     symbol[16];    // instrument code (fixed length, zero-padded)
    double   bid;           // best bid price
    double   ask;           // best ask price
    double   last;         // last traded price
    int64_t  volume;       // total volume
    double   timestamp;     // exchange timestamp
    double   local_ts;      // local receive timestamp
    uint32_t tick_count;   // sequence number
    uint8_t  flags;        // bit0: is_option, bit1: is_stale
    uint8_t  _pad[3];      // padding to 72 bytes
};
#pragma pack(pop)

static_assert(sizeof(FlatQuoteTickData) == 72,
              "FlatQuoteTickData must be 72 bytes");

// Wrapper that provides 64-byte alignment for cache-line optimization.
// The inner data is always 72 bytes; the wrapper adds tail padding to
// reach the next cache line boundary (128 bytes total: 64 + 72 rounded up).
struct alignas(64) FlatQuoteTick {
    FlatQuoteTickData data;
    uint8_t _align_pad[56] = {};  // pad to 128 bytes (2 cache lines)

    // Transparent forwarding to data members
    char* symbol() noexcept { return data.symbol; }
    const char* symbol() const noexcept { return data.symbol; }
    double& bid() noexcept { return data.bid; }
    double bid() const noexcept { return data.bid; }
    double& ask() noexcept { return data.ask; }
    double ask() const noexcept { return data.ask; }
    double& last() noexcept { return data.last; }
    double last() const noexcept { return data.last; }
    int64_t& volume() noexcept { return data.volume; }
    int64_t volume() const noexcept { return data.volume; }
    double& timestamp() noexcept { return data.timestamp; }
    double timestamp() const noexcept { return data.timestamp; }
    double& local_ts() noexcept { return data.local_ts; }
    double local_ts() const noexcept { return data.local_ts; }
    uint32_t& tick_count() noexcept { return data.tick_count; }
    uint32_t tick_count() const noexcept { return data.tick_count; }
    uint8_t& flags() noexcept { return data.flags; }
    uint8_t flags() const noexcept { return data.flags; }
};

static_assert(sizeof(FlatQuoteTick) == 128,
              "FlatQuoteTick wrapper must be 128 bytes (2 cache lines)");
static_assert(alignof(FlatQuoteTick) == 64,
              "FlatQuoteTick must be aligned to 64 bytes for cache-line optimization");

// ── FlatQuoteTick helper flags ─────────────────────────────────────────

namespace FlatQuoteFlags {
constexpr uint8_t IS_OPTION = 0x01;  // this is an option contract
constexpr uint8_t IS_STALE  = 0x02;  // tick is stale (exchange timeout)

inline bool is_option(const FlatQuoteTick& t) noexcept {
    return (t.flags() & IS_OPTION) != 0;
}
inline bool is_stale(const FlatQuoteTick& t) noexcept {
    return (t.flags() & IS_STALE) != 0;
}
inline void set_option(FlatQuoteTick& t) noexcept {
    t.flags() |= IS_OPTION;
}
inline void set_stale(FlatQuoteTick& t) noexcept {
    t.flags() |= IS_STALE;
}
}  // namespace FlatQuoteFlags

}  // namespace tyche
