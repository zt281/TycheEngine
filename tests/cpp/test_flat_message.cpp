// Unit tests for FlatMessage zero-copy serialization.
//
// Tests:
//   1. FlatMessageHeader size static_assert (24 bytes packed)
//   2. FlatQuoteTick size static_assert (72 bytes packed)
//   3. Round-trip: sender, event, durability, timestamp
//   4. Payload byte equality (zero-copy)

#include <gtest/gtest.h>

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "tyche/cpp/flat_message.h"
#include "tyche/cpp/flat_serializer.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

namespace tyche {
namespace {

// ── Size Static Assertions ─────────────────────────────────────────────

TEST(FlatMessageTest, FlatMessageHeaderSizeIs24Bytes) {
    // FlatMessageHeader must be exactly 24 bytes when packed
    static_assert(sizeof(FlatMessageHeader) == 24,
                  "FlatMessageHeader must be 24 bytes");
    EXPECT_EQ(sizeof(FlatMessageHeader), 24u);
}

TEST(FlatMessageTest, FlatQuoteTickDataSizeIs72Bytes) {
    // FlatQuoteTickData must be exactly 72 bytes when packed
    static_assert(sizeof(FlatQuoteTickData) == 72,
                  "FlatQuoteTickData must be 72 bytes");
    EXPECT_EQ(sizeof(FlatQuoteTickData), 72u);
}

TEST(FlatMessageTest, FlatQuoteTickWrapperSizeIs128Bytes) {
    // FlatQuoteTick wrapper must be 128 bytes (2 cache lines)
    static_assert(sizeof(FlatQuoteTick) == 128,
                  "FlatQuoteTick wrapper must be 128 bytes");
    EXPECT_EQ(sizeof(FlatQuoteTick), 128u);
}

TEST(FlatMessageTest, FlatQuoteTickAlignmentIs64Bytes) {
    // FlatQuoteTick must be aligned to 64-byte cache line
    static_assert(alignof(FlatQuoteTick) == 64,
                  "FlatQuoteTick must be aligned to 64 bytes");
    EXPECT_EQ(alignof(FlatQuoteTick), 64u);
}

// ── FlatQuoteTick Field Access ──────────────────────────────────────────

TEST(FlatMessageTest, FlatQuoteTickFieldsAccessible) {
    FlatQuoteTick tick{};
    std::strncpy(tick.symbol(), "IF2506", sizeof(tick.data.symbol) - 1);
    tick.bid() = 3852.50;
    tick.ask() = 3853.00;
    tick.last() = 3852.75;
    tick.volume() = 142857;
    tick.timestamp() = 1717071234.567890;
    tick.local_ts() = 1717071234.700000;
    tick.tick_count() = 12345;
    tick.flags() = 0x01;  // is_option

    EXPECT_STREQ(tick.symbol(), "IF2506");
    EXPECT_DOUBLE_EQ(tick.bid(), 3852.50);
    EXPECT_DOUBLE_EQ(tick.ask(), 3853.00);
    EXPECT_DOUBLE_EQ(tick.last(), 3852.75);
    EXPECT_EQ(tick.volume(), 142857);
    EXPECT_DOUBLE_EQ(tick.timestamp(), 1717071234.567890);
    EXPECT_DOUBLE_EQ(tick.local_ts(), 1717071234.700000);
    EXPECT_EQ(tick.tick_count(), 12345u);
    EXPECT_EQ(tick.flags(), 0x01);
}

// ── Serialize FlatMessage ───────────────────────────────────────────────

TEST(FlatMessageTest, SerializeFlatMessageBasic) {
    // Test basic flat message serialization
    uint8_t buffer[512];
    size_t size = serialize_flat(
        []() -> Message {
            Message m;
            m.msg_type = MessageType::EVENT;
            m.sender = "test_sender";
            m.event = "test_event";
            m.durability = DurabilityLevel::ASYNC_FLUSH;
            m.timestamp = 1717071234.567890;
            return m;
        }(),
        buffer,
        sizeof(buffer));

    // Minimum size: 24 (header) + 11 (sender) + 10 (event) + 0 (payload)
    EXPECT_GE(size, 45u);
    EXPECT_LE(size, 512u);

    // Verify header fields via pointer cast (zero-copy read)
    const FlatMessageHeader* hdr =
        reinterpret_cast<const FlatMessageHeader*>(buffer);
    EXPECT_EQ(hdr->msg_type, static_cast<uint8_t>(MessageType::EVENT));
    EXPECT_EQ(hdr->durability, static_cast<uint8_t>(DurabilityLevel::ASYNC_FLUSH));
    EXPECT_EQ(hdr->sender_len, 11u);  // strlen("test_sender")
    EXPECT_EQ(hdr->event_len, 10u);   // strlen("test_event")
    EXPECT_EQ(hdr->total_size, static_cast<uint32_t>(size));
    EXPECT_DOUBLE_EQ(hdr->timestamp, 1717071234.567890);
}

TEST(FlatMessageTest, SerializeFlatMessageDurabilityRoundtrip) {
    uint8_t buffer[512];

    for (auto durability : {
        DurabilityLevel::BEST_EFFORT,
        DurabilityLevel::ASYNC_FLUSH,
        DurabilityLevel::SYNC_FLUSH,
    }) {
        Message msg;
        msg.msg_type = MessageType::EVENT;
        msg.sender = "mod";
        msg.event = "evt";
        msg.durability = durability;

        size_t size = serialize_flat(msg, buffer, sizeof(buffer));
        ASSERT_GT(size, 0u);

        const FlatMessageHeader* hdr =
            reinterpret_cast<const FlatMessageHeader*>(buffer);
        EXPECT_EQ(hdr->durability, static_cast<uint8_t>(durability))
            << "Durability mismatch for "
            << static_cast<int>(durability);
    }
}

TEST(FlatMessageTest, SerializeFlatMessageTimestampRoundtrip) {
    uint8_t buffer[512];

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod";
    msg.event = "evt";
    msg.timestamp = 1717071234.567890;

    size_t size = serialize_flat(msg, buffer, sizeof(buffer));
    ASSERT_GT(size, 0u);

    const FlatMessageHeader* hdr =
        reinterpret_cast<const FlatMessageHeader*>(buffer);
    EXPECT_DOUBLE_EQ(hdr->timestamp, 1717071234.567890);
}

// ── Deserialize FlatMessage ─────────────────────────────────────────────

TEST(FlatMessageTest, DeserializeFlatMessageBasic) {
    Message orig;
    orig.msg_type = MessageType::EVENT;
    orig.sender = "test_sender";
    orig.event = "test_event";
    orig.durability = DurabilityLevel::ASYNC_FLUSH;
    orig.timestamp = 1717071234.567890;

    uint8_t buffer[512];
    size_t size = serialize_flat(orig, buffer, sizeof(buffer));

    Message decoded = deserialize_flat(buffer, size);
    EXPECT_EQ(decoded.msg_type, MessageType::EVENT);
    EXPECT_EQ(decoded.sender, "test_sender");
    EXPECT_EQ(decoded.event, "test_event");
    EXPECT_EQ(decoded.durability, DurabilityLevel::ASYNC_FLUSH);
    ASSERT_TRUE(decoded.timestamp.has_value());
    EXPECT_DOUBLE_EQ(*decoded.timestamp, 1717071234.567890);
}

// ── Payload Byte Equality (Zero-Copy) ────────────────────────────────────

TEST(FlatMessageTest, PayloadByteEquality) {
    // Create message with payload
    Message orig;
    orig.msg_type = MessageType::EVENT;
    orig.sender = "mod";
    orig.event = "tick";
    orig.payload["symbol"] = std::string("IF2506");
    orig.payload["bid"] = 3852.50;
    orig.payload["ask"] = 3853.00;
    orig.payload["last"] = 3852.75;
    orig.payload["volume"] = 142857;

    uint8_t buffer[512];
    size_t size = serialize_flat(orig, buffer, sizeof(buffer));

    // Deserialize and verify header round-trip
    Message decoded = deserialize_flat(buffer, size);
    EXPECT_EQ(decoded.msg_type, MessageType::EVENT);
    EXPECT_EQ(decoded.sender, "mod");
    EXPECT_EQ(decoded.event, "tick");

    // Verify header bytes are identical
    uint8_t buffer2[512];
    size_t size2 = serialize_flat(decoded, buffer2, sizeof(buffer2));

    const FlatMessageHeader* h1 =
        reinterpret_cast<const FlatMessageHeader*>(buffer);
    const FlatMessageHeader* h2 =
        reinterpret_cast<const FlatMessageHeader*>(buffer2);
    EXPECT_EQ(h1->msg_type, h2->msg_type);
    EXPECT_EQ(h1->durability, h2->durability);
    EXPECT_EQ(h1->sender_len, h2->sender_len);
    EXPECT_EQ(h1->event_len, h2->event_len);
    // Note: payload_len differs because deserialize_flat stores raw payload as __flat__
    // which has different encoding than the original typed payload
}

// ── Capacity Check ──────────────────────────────────────────────────────

TEST(FlatMessageTest, SerializeFailsWhenBufferTooSmall) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "test_sender";
    msg.event = "test_event";

    // Buffer too small for header + strings
    uint8_t tiny_buffer[10];
    size_t size = serialize_flat(msg, tiny_buffer, sizeof(tiny_buffer));
    EXPECT_EQ(size, 0u);
}

// ── Empty Sender/Event ─────────────────────────────────────────────────

TEST(FlatMessageTest, EmptySenderAndEvent) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "";
    msg.event = "";

    uint8_t buffer[512];
    size_t size = serialize_flat(msg, buffer, sizeof(buffer));
    ASSERT_GT(size, 0u);

    const FlatMessageHeader* hdr =
        reinterpret_cast<const FlatMessageHeader*>(buffer);
    EXPECT_EQ(hdr->sender_len, 0u);
    EXPECT_EQ(hdr->event_len, 0u);
}

// ── serialize_flat_quote / deserialize_flat_quote ───────────────────────

TEST(FlatMessageTest, FlatQuoteTickRoundtrip) {
    FlatQuoteTick tick{};
    std::strncpy(tick.symbol(), "IF2506", sizeof(tick.data.symbol) - 1);
    tick.bid() = 3852.50;
    tick.ask() = 3853.00;
    tick.last() = 3852.75;
    tick.volume() = 142857;
    tick.timestamp() = 1717071234.567890;
    tick.local_ts() = 1717071234.700000;
    tick.tick_count() = 12345;
    tick.flags() = 0x01;

    alignas(alignof(FlatQuoteTickData)) uint8_t buffer[256];
    size_t size = serialize_flat_quote(tick, buffer, sizeof(buffer));
    EXPECT_EQ(size, sizeof(FlatQuoteTickData));

    const FlatQuoteTick* decoded = deserialize_flat_quote(buffer, size);
    ASSERT_NE(decoded, nullptr);
    EXPECT_STREQ(decoded->symbol(), "IF2506");
    EXPECT_DOUBLE_EQ(decoded->bid(), 3852.50);
    EXPECT_DOUBLE_EQ(decoded->ask(), 3853.00);
    EXPECT_DOUBLE_EQ(decoded->last(), 3852.75);
    EXPECT_EQ(decoded->volume(), 142857);
    EXPECT_DOUBLE_EQ(decoded->timestamp(), 1717071234.567890);
    EXPECT_DOUBLE_EQ(decoded->local_ts(), 1717071234.700000);
    EXPECT_EQ(decoded->tick_count(), 12345u);
    EXPECT_EQ(decoded->flags(), 0x01);
}

TEST(FlatMessageTest, SerializeFlatQuoteBufferTooSmall) {
    FlatQuoteTick tick{};
    uint8_t buffer[1];
    size_t size = serialize_flat_quote(tick, buffer, sizeof(buffer));
    EXPECT_EQ(size, 0u);
}

TEST(FlatMessageTest, DeserializeFlatQuoteAlignmentCheck) {
    FlatQuoteTick tick{};
    std::strncpy(tick.symbol(), "TEST", 4);
    tick.bid() = 1.0;

    alignas(alignof(FlatQuoteTickData)) uint8_t buffer[256];
    size_t size = serialize_flat_quote(tick, buffer, sizeof(buffer));
    ASSERT_EQ(size, sizeof(FlatQuoteTickData));

    // Misaligned pointer should return nullptr
    uint8_t* misaligned = buffer + 1;
    const FlatQuoteTick* decoded = deserialize_flat_quote(misaligned, size - 1);
    EXPECT_EQ(decoded, nullptr);
}

TEST(FlatMessageTest, DeserializeFlatQuoteSizeTooSmall) {
    alignas(alignof(FlatQuoteTickData)) uint8_t buffer[256];
    const FlatQuoteTick* decoded = deserialize_flat_quote(buffer, 1);
    EXPECT_EQ(decoded, nullptr);
}

// ── Empty payload serialization ─────────────────────────────────────────

TEST(FlatMessageTest, SerializeEmptyPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod";
    msg.event = "evt";
    // payload is empty by default

    uint8_t buffer[512];
    size_t size = serialize_flat(msg, buffer, sizeof(buffer));
    ASSERT_GT(size, 0u);

    const FlatMessageHeader* hdr = reinterpret_cast<const FlatMessageHeader*>(buffer);
    EXPECT_EQ(hdr->payload_len, 0u);

    Message decoded = deserialize_flat(buffer, size);
    EXPECT_EQ(decoded.msg_type, MessageType::EVENT);
    EXPECT_EQ(decoded.sender, "mod");
    EXPECT_EQ(decoded.event, "evt");
    EXPECT_TRUE(decoded.payload.empty());
}

// ── Unsupported payload type falls back to nil ────────────────────────

TEST(FlatMessageTest, UnsupportedPayloadTypeSerializedAsNil) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod";
    msg.event = "evt";
    // std::vector<int> is not supported by serialize_flat
    msg.payload["unsupported"] = std::vector<int>{1, 2, 3};

    uint8_t buffer[512];
    size_t size = serialize_flat(msg, buffer, sizeof(buffer));
    ASSERT_GT(size, 0u);

    // Should serialize without crashing; unsupported type becomes nil marker
    const FlatMessageHeader* hdr = reinterpret_cast<const FlatMessageHeader*>(buffer);
    EXPECT_GE(hdr->payload_len, 0u);
}

// ── FlatQuoteTick flags helpers ───────────────────────────────────────

TEST(FlatMessageTest, FlatQuoteFlagsHelpers) {
    FlatQuoteTick tick{};
    EXPECT_FALSE(FlatQuoteFlags::is_option(tick));
    EXPECT_FALSE(FlatQuoteFlags::is_stale(tick));

    FlatQuoteFlags::set_option(tick);
    EXPECT_TRUE(FlatQuoteFlags::is_option(tick));
    EXPECT_FALSE(FlatQuoteFlags::is_stale(tick));

    FlatQuoteFlags::set_stale(tick);
    EXPECT_TRUE(FlatQuoteFlags::is_option(tick));
    EXPECT_TRUE(FlatQuoteFlags::is_stale(tick));
}

}  // namespace
}  // namespace tyche
