// Unit tests for tyche types: ModuleId, enums, Endpoint, string conversions.

#include <gtest/gtest.h>

#include <regex>
#include <set>
#include <string>

#include "tyche/cpp/types.h"

namespace tyche {
namespace {

// ── ModuleId Generation ───────────────────────────────────────────────

TEST(ModuleIdTest, GenerateFormat) {
    std::string id = ModuleId::generate("gateway");

    // Should match: gateway_[6 hex chars]
    std::regex pattern("gateway_[0-9a-f]{6}");
    EXPECT_TRUE(std::regex_match(id, pattern)) << "Got: " << id;
}

TEST(ModuleIdTest, GenerateWithDifferentFamilies) {
    std::string id1 = ModuleId::generate("greeks");
    std::string id2 = ModuleId::generate("static_data");

    EXPECT_TRUE(id1.find("greeks_") == 0);
    EXPECT_TRUE(id2.find("static_data_") == 0);
}

TEST(ModuleIdTest, GenerateDefaultFamily) {
    std::string id = ModuleId::generate();
    EXPECT_TRUE(id.find("unknown_") == 0);
}

TEST(ModuleIdTest, GenerateUniqueness) {
    std::set<std::string> ids;
    for (int i = 0; i < 100; ++i) {
        ids.insert(ModuleId::generate("test"));
    }
    // With 24 bits of randomness, 100 IDs should be unique
    EXPECT_EQ(ids.size(), 100u);
}

// ── MessageType String Conversion ─────────────────────────────────────

TEST(TypesTest, MessageTypeToStr) {
    EXPECT_STREQ(message_type_to_str(MessageType::COMMAND), "cmd");
    EXPECT_STREQ(message_type_to_str(MessageType::EVENT), "evt");
    EXPECT_STREQ(message_type_to_str(MessageType::HEARTBEAT), "hbt");
    EXPECT_STREQ(message_type_to_str(MessageType::REGISTER), "reg");
    EXPECT_STREQ(message_type_to_str(MessageType::ACK), "ack");
    EXPECT_STREQ(message_type_to_str(MessageType::RESPONSE), "resp");
    EXPECT_STREQ(message_type_to_str(MessageType::REQUEST), "req");
}

TEST(TypesTest, MessageTypeFromStr) {
    EXPECT_EQ(message_type_from_str("cmd"), MessageType::COMMAND);
    EXPECT_EQ(message_type_from_str("evt"), MessageType::EVENT);
    EXPECT_EQ(message_type_from_str("hbt"), MessageType::HEARTBEAT);
    EXPECT_EQ(message_type_from_str("reg"), MessageType::REGISTER);
    EXPECT_EQ(message_type_from_str("ack"), MessageType::ACK);
    EXPECT_EQ(message_type_from_str("resp"), MessageType::RESPONSE);
    EXPECT_EQ(message_type_from_str("req"), MessageType::REQUEST);
}

TEST(TypesTest, MessageTypeFromStrUnknownDefaultsToEvent) {
    EXPECT_EQ(message_type_from_str("unknown"), MessageType::EVENT);
    EXPECT_EQ(message_type_from_str(""), MessageType::EVENT);
}

// ── InterfacePattern String Conversion ────────────────────────────────

TEST(TypesTest, InterfacePatternToStr) {
    EXPECT_STREQ(interface_pattern_to_str(InterfacePattern::ON), "on");
    EXPECT_STREQ(interface_pattern_to_str(InterfacePattern::SEND), "send");
    EXPECT_STREQ(interface_pattern_to_str(InterfacePattern::HANDLE), "handle");
    EXPECT_STREQ(interface_pattern_to_str(InterfacePattern::REQUEST), "request");
}

TEST(TypesTest, InterfacePatternFromStr) {
    EXPECT_EQ(interface_pattern_from_str("on"), InterfacePattern::ON);
    EXPECT_EQ(interface_pattern_from_str("send"), InterfacePattern::SEND);
    EXPECT_EQ(interface_pattern_from_str("handle"), InterfacePattern::HANDLE);
    EXPECT_EQ(interface_pattern_from_str("request"), InterfacePattern::REQUEST);
}

TEST(TypesTest, InterfacePatternFromStrUnknownDefaultsToOn) {
    EXPECT_EQ(interface_pattern_from_str("foo"), InterfacePattern::ON);
    EXPECT_EQ(interface_pattern_from_str(""), InterfacePattern::ON);
}

// ── Endpoint ──────────────────────────────────────────────────────────

TEST(EndpointTest, DefaultConstruction) {
    Endpoint ep;
    EXPECT_EQ(ep.host, "");
    EXPECT_EQ(ep.port, 0);
}

TEST(EndpointTest, ParameterizedConstruction) {
    Endpoint ep("127.0.0.1", 5555);
    EXPECT_EQ(ep.host, "127.0.0.1");
    EXPECT_EQ(ep.port, 5555);
}

TEST(EndpointTest, ToString) {
    Endpoint ep("127.0.0.1", 5555);
    EXPECT_EQ(ep.to_string(), "tcp://127.0.0.1:5555");

    Endpoint ep2("0.0.0.0", 8080);
    EXPECT_EQ(ep2.to_string(), "tcp://0.0.0.0:8080");
}

// ── Interface Struct ──────────────────────────────────────────────────

TEST(InterfaceTest, DefaultValues) {
    Interface iface;
    EXPECT_EQ(iface.pattern, InterfacePattern::ON);
    EXPECT_EQ(iface.durability, DurabilityLevel::ASYNC_FLUSH);
    EXPECT_EQ(iface.backpressure, BackpressureStrategy::DROP_OLDEST);
    EXPECT_EQ(iface.max_queue_depth, 10000);
}

// ── Constants ─────────────────────────────────────────────────────────

TEST(TypesTest, HeartbeatConstants) {
    EXPECT_DOUBLE_EQ(HEARTBEAT_INTERVAL, 1.0);
    EXPECT_EQ(HEARTBEAT_LIVENESS, 3);
    // Admin port is base_port + 3 (registration=5555 → admin=5558),
    // matching the port layout documented in src/tyche/cpp/engine/main.cpp.
    EXPECT_EQ(ADMIN_PORT_DEFAULT, 5558);
}

// ── DurabilityLevel Values ────────────────────────────────────────────

TEST(TypesTest, DurabilityLevelValues) {
    EXPECT_EQ(static_cast<int>(DurabilityLevel::BEST_EFFORT), 0);
    EXPECT_EQ(static_cast<int>(DurabilityLevel::ASYNC_FLUSH), 1);
    EXPECT_EQ(static_cast<int>(DurabilityLevel::SYNC_FLUSH), 2);
}

}  // namespace
}  // namespace tyche
