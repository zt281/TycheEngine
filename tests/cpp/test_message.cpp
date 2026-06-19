// Unit tests for tyche::Message serialization/deserialization.

#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

namespace tyche {
namespace {

// ── Basic Serialize/Deserialize Round-trip ─────────────────────────────

TEST(MessageTest, EmptyMessageRoundtrip) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "test_sender";
    msg.event = "test_event";

    auto bytes = serialize(msg);
    ASSERT_FALSE(bytes.empty());

    Message decoded = deserialize(bytes.data(), bytes.size());
    EXPECT_EQ(decoded.msg_type, MessageType::EVENT);
    EXPECT_EQ(decoded.sender, "test_sender");
    EXPECT_EQ(decoded.event, "test_event");
    EXPECT_TRUE(decoded.payload.empty());
    EXPECT_FALSE(decoded.recipient.has_value());
    EXPECT_FALSE(decoded.correlation_id.has_value());
}

TEST(MessageTest, AllMessageTypesRoundtrip) {
    std::vector<MessageType> types = {
        MessageType::COMMAND,
        MessageType::EVENT,
        MessageType::HEARTBEAT,
        MessageType::REGISTER,
        MessageType::ACK,
        MessageType::RESPONSE,
        MessageType::REQUEST,
    };

    for (auto t : types) {
        Message msg;
        msg.msg_type = t;
        msg.sender = "s";
        msg.event = "e";

        auto bytes = serialize(msg);
        Message decoded = deserialize(bytes.data(), bytes.size());
        EXPECT_EQ(decoded.msg_type, t);
    }
}

// ── Payload Types ─────────────────────────────────────────────────────

TEST(MessageTest, StringPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "tick";
    msg.payload["symbol"] = std::string("AAPL");
    msg.payload["exchange"] = std::string("NASDAQ");

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    EXPECT_EQ(decoded.payload.size(), 2u);
    EXPECT_EQ(std::any_cast<std::string>(decoded.payload["symbol"]), "AAPL");
    EXPECT_EQ(std::any_cast<std::string>(decoded.payload["exchange"]), "NASDAQ");
}

TEST(MessageTest, IntPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "data";
    msg.payload["count"] = 42;
    msg.payload["negative"] = -10;

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    EXPECT_EQ(std::any_cast<int>(decoded.payload["count"]), 42);
    EXPECT_EQ(std::any_cast<int>(decoded.payload["negative"]), -10);
}

TEST(MessageTest, DoublePayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "price";
    msg.payload["bid"] = 3.14;
    msg.payload["ask"] = 2.718;

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    EXPECT_DOUBLE_EQ(std::any_cast<double>(decoded.payload["bid"]), 3.14);
    EXPECT_DOUBLE_EQ(std::any_cast<double>(decoded.payload["ask"]), 2.718);
}

TEST(MessageTest, BoolPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "status";
    msg.payload["active"] = true;
    msg.payload["paused"] = false;

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    EXPECT_EQ(std::any_cast<bool>(decoded.payload["active"]), true);
    EXPECT_EQ(std::any_cast<bool>(decoded.payload["paused"]), false);
}

TEST(MessageTest, NullPayloadValue) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "test";
    msg.payload["null_field"] = std::any{};  // empty any = null

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    // Null values may not appear in deserialized payload (or appear as empty any)
    // This tests that serialization doesn't crash
    EXPECT_TRUE(bytes.size() > 0);
}

TEST(MessageTest, NestedPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "nested";

    Payload inner;
    inner["key1"] = std::string("value1");
    inner["key2"] = 100;
    msg.payload["nested"] = std::any(inner);

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    auto nested = std::any_cast<Payload>(decoded.payload["nested"]);
    EXPECT_EQ(std::any_cast<std::string>(nested["key1"]), "value1");
    EXPECT_EQ(std::any_cast<int>(nested["key2"]), 100);
}

TEST(MessageTest, VectorStringPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "list";
    msg.payload["items"] = std::vector<std::string>{"alpha", "beta", "gamma"};

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());

    auto items = std::any_cast<std::vector<std::string>>(decoded.payload["items"]);
    ASSERT_EQ(items.size(), 3u);
    EXPECT_EQ(items[0], "alpha");
    EXPECT_EQ(items[1], "beta");
    EXPECT_EQ(items[2], "gamma");
}

// ── Optional Fields ───────────────────────────────────────────────────

TEST(MessageTest, RecipientField) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "directed";
    msg.recipient = "mod_b";

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    ASSERT_TRUE(decoded.recipient.has_value());
    EXPECT_EQ(*decoded.recipient, "mod_b");
}

TEST(MessageTest, CorrelationIdField) {
    Message msg;
    msg.msg_type = MessageType::REQUEST;
    msg.sender = "mod_a";
    msg.event = "query";
    msg.correlation_id = "abc-123-def-456";

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    ASSERT_TRUE(decoded.correlation_id.has_value());
    EXPECT_EQ(*decoded.correlation_id, "abc-123-def-456");
}

TEST(MessageTest, TimestampField) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "timed";
    msg.timestamp = 1716633600.123;

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    ASSERT_TRUE(decoded.timestamp.has_value());
    EXPECT_DOUBLE_EQ(*decoded.timestamp, 1716633600.123);
}

TEST(MessageTest, TimeoutFields) {
    Message msg;
    msg.msg_type = MessageType::REQUEST;
    msg.sender = "mod_a";
    msg.event = "job";
    msg.wait_timeout = 5.0f;
    msg.run_timeout = 30.0f;

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    ASSERT_TRUE(decoded.wait_timeout.has_value());
    ASSERT_TRUE(decoded.run_timeout.has_value());
    EXPECT_FLOAT_EQ(*decoded.wait_timeout, 5.0f);
    EXPECT_FLOAT_EQ(*decoded.run_timeout, 30.0f);
}

// ── Durability Level ──────────────────────────────────────────────────

TEST(MessageTest, DurabilityLevelRoundtrip) {
    std::vector<DurabilityLevel> levels = {
        DurabilityLevel::BEST_EFFORT,
        DurabilityLevel::ASYNC_FLUSH,
        DurabilityLevel::SYNC_FLUSH,
    };

    for (auto lvl : levels) {
        Message msg;
        msg.msg_type = MessageType::EVENT;
        msg.sender = "s";
        msg.event = "e";
        msg.durability = lvl;

        auto bytes = serialize(msg);
        Message decoded = deserialize(bytes.data(), bytes.size());
        EXPECT_EQ(decoded.durability, lvl);
    }
}

// ── Void pointer deserialize overload ─────────────────────────────────

TEST(MessageTest, DeserializeFromVoidPointer) {
    Message msg;
    msg.msg_type = MessageType::HEARTBEAT;
    msg.sender = "hb_module";
    msg.event = "heartbeat";

    auto bytes = serialize(msg);
    Message decoded = deserialize(static_cast<const void*>(bytes.data()), bytes.size());
    EXPECT_EQ(decoded.msg_type, MessageType::HEARTBEAT);
    EXPECT_EQ(decoded.sender, "hb_module");
}

// ── Large Payload ─────────────────────────────────────────────────────

TEST(MessageTest, LargePayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "bulk";

    for (int i = 0; i < 100; ++i) {
        msg.payload["key_" + std::to_string(i)] = std::string("value_" + std::to_string(i));
    }

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    EXPECT_EQ(decoded.payload.size(), 100u);
    EXPECT_EQ(std::any_cast<std::string>(decoded.payload["key_50"]), "value_50");
}

TEST(MessageTest, AllAnyTypesInPayload) {
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "type_test";
    msg.event = "all_types";

    // Cover various pack_any branches
    msg.payload["str"] = std::string("hello");
    msg.payload["cstr"] = "const_char_star";
    msg.payload["bool_t"] = true;
    msg.payload["bool_f"] = false;
    msg.payload["int"] = 42;
    msg.payload["int64"] = int64_t{-9007199254740992LL};
    msg.payload["uint64"] = uint64_t{18446744073709551615ULL};
    msg.payload["double"] = 3.141592653589793;
    msg.payload["float"] = 2.7182818f;
    msg.payload["empty_any"] = std::any{};

    // Nested Payload map
    Payload nested;
    nested["inner_key"] = std::string("inner_value");
    msg.payload["nested"] = nested;

    // Vector of std::string
    std::vector<std::string> vec_str{"a", "b", "c"};
    msg.payload["vec_str"] = vec_str;

    // Vector of std::any (mixed array)
    std::vector<std::any> vec_any;
    vec_any.push_back(std::string("vec_str"));
    vec_any.push_back(123);
    vec_any.push_back(4.56);
    msg.payload["vec_any"] = vec_any;

    // Should not throw during serialization
    EXPECT_NO_THROW({
        auto bytes = serialize(msg);
        EXPECT_FALSE(bytes.empty());
    });
}

TEST(MessageTest, UnknownTypePacksAsNil) {
    // Verify that empty any packs as nil and deserializes correctly
    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "s";
    msg.event = "e";
    msg.payload["nil"] = std::any{};

    auto bytes = serialize(msg);
    Message decoded = deserialize(bytes.data(), bytes.size());
    // Empty any -> nil -> empty any on deserialize
    EXPECT_FALSE(decoded.payload["nil"].has_value());
}

}  // namespace
}  // namespace tyche
