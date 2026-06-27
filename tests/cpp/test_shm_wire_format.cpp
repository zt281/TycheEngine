// Unit tests: verify that the new optimized write_shm_quote_tick() path
// produces byte-identical msgpack wire format to the old path
// (tick_to_payload() + write_shm_event()).
//
// Also verifies that tyche::serialize() and tyche::serialize_tls() produce
// byte-identical output for the same Message.

#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "modules/ctp_gateway_cpp/src/quote_tick.h"
#include "modules/ctp_gateway_cpp/src/shm_writer.h"
#include "tyche/cpp/engine/shared_memory_queue.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

namespace {

// ── QuoteTick test fixture helper ──────────────────────────────────────

QuoteTick make_test_tick(const char* instrument_id,
                          const char* exchange_id,
                          const char* update_time,
                          const char* trading_day,
                          double last_price,
                          double bid_price1,
                          double ask_price1,
                          int32_t bid_volume1,
                          int32_t ask_volume1,
                          int32_t volume,
                          double open_interest,
                          double turnover,
                          double upper_limit,
                          double lower_limit,
                          double open_price,
                          double high_price,
                          double low_price,
                          double pre_settle,
                          int32_t update_millisec) {
    QuoteTick tick{};
    std::memset(&tick, 0, sizeof(tick));
    std::strncpy(tick.instrument_id, instrument_id, sizeof(tick.instrument_id) - 1);
    std::strncpy(tick.exchange_id, exchange_id, sizeof(tick.exchange_id) - 1);
    std::strncpy(tick.update_time, update_time, sizeof(tick.update_time) - 1);
    std::strncpy(tick.trading_day, trading_day, sizeof(tick.trading_day) - 1);
    tick.last_price        = last_price;
    tick.bid_price1        = bid_price1;
    tick.ask_price1        = ask_price1;
    tick.bid_volume1       = bid_volume1;
    tick.ask_volume1       = ask_volume1;
    tick.volume            = volume;
    tick.open_interest     = open_interest;
    tick.turnover          = turnover;
    tick.upper_limit_price = upper_limit;
    tick.lower_limit_price = lower_limit;
    tick.open_price        = open_price;
    tick.high_price        = high_price;
    tick.low_price         = low_price;
    tick.pre_settle_price  = pre_settle;
    tick.update_millisec   = update_millisec;
    tick.receive_ts_ns     = 1700000000000000000ULL;
    return tick;
}

QuoteTick make_basic_tick() {
    return make_test_tick(
        "ag2501C5000", "SHFE", "09:30:15", "20250115",
        5000.0, 4999.0, 5001.0, 100, 200, 50000,
        123456.0, 250000000.0, 5500.0, 4500.0,
        4980.0, 5020.0, 4975.0, 4990.0, 500);
}

QuoteTick make_empty_tick() {
    return make_test_tick(
        "", "", "", "",
        0.0, 0.0, 0.0, 0, 0, 0,
        0.0, 0.0, 0.0, 0.0,
        0.0, 0.0, 0.0, 0.0, 0);
}

QuoteTick make_extreme_tick() {
    return make_test_tick(
        "ZZ9999Z999", "DCE", "23:59:59", "20991231",
        1e15, -1e15, 1.7e308, INT32_MAX, INT32_MAX, INT32_MAX,
        1.7e308, 1.7e308, 1e15, -1e15,
        -0.0, 1.7e308, -1.7e308, 1e-15, INT32_MAX);
}

// Build a Payload from a QuoteTick mirroring tick_to_payload() / write_shm_quote_tick()
// field mapping exactly.  This is the reference field mapping under test.
tyche::Payload build_payload_from_tick(const QuoteTick& tick) {
    tyche::Payload payload;
    payload["instrument_id"] = std::string(tick.instrument_id_sv());
    payload["exchange_id"]   = std::string(tick.exchange_id);
    payload["last_price"]    = tick.last_price;
    payload["volume"]        = tick.volume;
    payload["bid_price1"]    = tick.bid_price1;
    payload["bid_volume1"]   = tick.bid_volume1;
    payload["ask_price1"]    = tick.ask_price1;
    payload["ask_volume1"]   = tick.ask_volume1;
    payload["upper_limit"]   = tick.upper_limit_price;
    payload["lower_limit"]   = tick.lower_limit_price;
    payload["open_price"]    = tick.open_price;
    payload["high_price"]    = tick.high_price;
    payload["low_price"]     = tick.low_price;
    payload["pre_settle"]    = tick.pre_settle_price;
    payload["open_interest"] = tick.open_interest;
    payload["turnover"]      = tick.turnover;
    payload["update_time"]   = std::string(tick.update_time);
    payload["update_millisec"] = tick.update_millisec;
    payload["trading_day"]   = std::string(tick.trading_day);
    return payload;
}

// Old-path wire bytes: write_shm_event(queue, topic, sender, payload)
std::vector<uint8_t> old_path_wire(const std::string& shm_name,
                                    const std::string& topic,
                                    const std::string& sender,
                                    const tyche::Payload& payload) {
    tyche::SharedMemoryQueue q({shm_name, 16, 4096}, true);
    if (!q.is_valid()) return {};
    write_shm_event(&q, topic, sender, payload);
    auto result = q.read();
    return result.value_or(std::vector<uint8_t>{});
}

// New-path wire bytes: write_shm_quote_tick(queue, sender, tick)
std::vector<uint8_t> new_path_wire(const std::string& shm_name,
                                    const std::string& sender,
                                    const QuoteTick& tick) {
    tyche::SharedMemoryQueue q({shm_name, 16, 4096}, true);
    if (!q.is_valid()) return {};
    write_shm_quote_tick(&q, sender, tick);
    auto result = q.read();
    return result.value_or(std::vector<uint8_t>{});
}

// ═══════════════════════════════════════════════════════════════════════
// Layer 1: serialize() vs serialize_tls() byte-identical output
// ═══════════════════════════════════════════════════════════════════════

class SerializeConsistencyTest : public ::testing::TestWithParam<QuoteTick> {};

TEST_P(SerializeConsistencyTest, SerializeMatchesSerializeTls) {
    const QuoteTick tick = GetParam();
    auto payload = build_payload_from_tick(tick);

    tyche::Message msg;
    msg.msg_type = tyche::MessageType::EVENT;
    msg.sender   = "ctp_gateway_cpp_a1b2c3";
    msg.event    = "send_compute_greeks";
    msg.payload  = payload;

    auto heap_bytes = tyche::serialize(msg);
    auto tls_view   = tyche::serialize_tls(msg);

    ASSERT_FALSE(heap_bytes.empty());
    ASSERT_GT(tls_view.size, 0u);
    ASSERT_EQ(heap_bytes.size(), tls_view.size)
        << "serialize() and serialize_tls() produced different sizes";

    std::vector<uint8_t> tls_bytes(tls_view.data, tls_view.data + tls_view.size);
    EXPECT_EQ(heap_bytes, tls_bytes)
        << "serialize() and serialize_tls() produced different byte content";
}

INSTANTIATE_TEST_SUITE_P(
    ShmWireFormat,
    SerializeConsistencyTest,
    ::testing::Values(
        make_basic_tick(),
        make_empty_tick(),
        make_extreme_tick()
    ),
    [](const ::testing::TestParamInfo<QuoteTick>& info) {
        const auto& t = info.param;
        if (t.instrument_id[0] == '\0') return std::string("EmptyStrings");
        if (t.last_price > 1e14)        return std::string("ExtremeValues");
        return std::string("BasicTick");
    });

// ═══════════════════════════════════════════════════════════════════════
// Layer 2: Full SHM wire format — write_shm_event vs write_shm_quote_tick
// ═══════════════════════════════════════════════════════════════════════

class ShmWireFormatTest : public ::testing::TestWithParam<QuoteTick> {};

TEST_P(ShmWireFormatTest, OldAndNewPathProduceIdenticalWireBytes) {
    const QuoteTick tick = GetParam();
    auto payload = build_payload_from_tick(tick);

    // Unique SHM names per parameter to avoid cross-test interference
    const auto idx = ::testing::UnitTest::GetInstance()
                         ->current_test_info()
                         ->value_param();
    std::string suffix = (idx != nullptr) ? idx : "default";
    std::string old_shm = "shm_wire_old_" + suffix;
    std::string new_shm = "shm_wire_new_" + suffix;

    auto old_bytes = old_path_wire(old_shm, "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire(new_shm, "ctp_gateway_cpp_test", tick);

    ASSERT_FALSE(old_bytes.empty()) << "Old path (write_shm_event) returned empty bytes";
    ASSERT_FALSE(new_bytes.empty()) << "New path (write_shm_quote_tick) returned empty bytes";
    ASSERT_EQ(old_bytes.size(), new_bytes.size())
        << "Wire format size mismatch: old=" << old_bytes.size()
        << " new=" << new_bytes.size();
    EXPECT_EQ(old_bytes, new_bytes)
        << "Wire format byte mismatch between old and new SHM paths";
}

INSTANTIATE_TEST_SUITE_P(
    ShmWireFormat,
    ShmWireFormatTest,
    ::testing::Values(
        make_basic_tick(),
        make_empty_tick(),
        make_extreme_tick()
    ),
    [](const ::testing::TestParamInfo<QuoteTick>& info) {
        const auto& t = info.param;
        if (t.instrument_id[0] == '\0') return std::string("EmptyStrings");
        if (t.last_price > 1e14)        return std::string("ExtremeValues");
        return std::string("BasicTick");
    });

// ═══════════════════════════════════════════════════════════════════════
// Layer 3: Individual named tests for clarity and diagnostics
// ═══════════════════════════════════════════════════════════════════════

TEST(ShmWireFormatNamedTest, BasicTickFieldMapping) {
    auto tick    = make_basic_tick();
    auto payload = build_payload_from_tick(tick);

    // Verify key fields are present and correctly typed
    EXPECT_EQ(std::any_cast<std::string>(payload["instrument_id"]), "ag2501C5000");
    EXPECT_EQ(std::any_cast<std::string>(payload["exchange_id"]),   "SHFE");
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["last_price"]),  5000.0);
    EXPECT_EQ(std::any_cast<int>(payload["volume"]),                50000);
    EXPECT_EQ(std::any_cast<int>(payload["bid_volume1"]),           100);
    EXPECT_EQ(std::any_cast<int>(payload["ask_volume1"]),           200);
    EXPECT_EQ(std::any_cast<int>(payload["update_millisec"]),       500);
    EXPECT_EQ(std::any_cast<std::string>(payload["trading_day"]),   "20250115");
    EXPECT_EQ(std::any_cast<std::string>(payload["update_time"]),   "09:30:15");

    // SHM wire format comparison
    auto old_bytes = old_path_wire("shm_basic_old", "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire("shm_basic_new", "ctp_gateway_cpp_test", tick);

    ASSERT_EQ(old_bytes.size(), new_bytes.size());
    EXPECT_EQ(old_bytes, new_bytes);
}

TEST(ShmWireFormatNamedTest, EmptyStringsAllZeros) {
    auto tick    = make_empty_tick();
    auto payload = build_payload_from_tick(tick);

    // Empty strings should produce empty std::string values
    EXPECT_EQ(std::any_cast<std::string>(payload["instrument_id"]), "");
    EXPECT_EQ(std::any_cast<std::string>(payload["exchange_id"]),   "");
    EXPECT_EQ(std::any_cast<std::string>(payload["update_time"]),   "");
    EXPECT_EQ(std::any_cast<std::string>(payload["trading_day"]),   "");

    auto old_bytes = old_path_wire("shm_empty_old", "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire("shm_empty_new", "ctp_gateway_cpp_test", tick);

    ASSERT_EQ(old_bytes.size(), new_bytes.size());
    EXPECT_EQ(old_bytes, new_bytes);
}

TEST(ShmWireFormatNamedTest, ExtremeValues) {
    auto tick    = make_extreme_tick();
    auto payload = build_payload_from_tick(tick);

    // Verify extreme values survive payload construction
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["last_price"]),  1e15);
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["bid_price1"]), -1e15);
    EXPECT_EQ(std::any_cast<int>(payload["bid_volume1"]),           INT32_MAX);
    EXPECT_EQ(std::any_cast<int>(payload["volume"]),                INT32_MAX);

    auto old_bytes = old_path_wire("shm_extreme_old", "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire("shm_extreme_new", "ctp_gateway_cpp_test", tick);

    ASSERT_EQ(old_bytes.size(), new_bytes.size());
    EXPECT_EQ(old_bytes, new_bytes);
}

TEST(ShmWireFormatNamedTest, SpecialCharactersInInstrumentId) {
    auto tick = make_test_tick(
        "IO2501-C-4000", "CFFEX", "14:59:59", "20250120",
        123.456, 123.0, 124.0, 50, 60, 12345,
        99999.0, 1e9, 200.0, 50.0,
        100.0, 150.0, 90.0, 95.0, 123);

    auto payload = build_payload_from_tick(tick);

    EXPECT_EQ(std::any_cast<std::string>(payload["instrument_id"]), "IO2501-C-4000");
    EXPECT_EQ(std::any_cast<std::string>(payload["exchange_id"]),   "CFFEX");

    auto old_bytes = old_path_wire("shm_special_old", "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire("shm_special_new", "ctp_gateway_cpp_test", tick);

    ASSERT_EQ(old_bytes.size(), new_bytes.size());
    EXPECT_EQ(old_bytes, new_bytes);
}

TEST(ShmWireFormatNamedTest, NegativePricesAndZeroVolumes) {
    auto tick = make_test_tick(
        "m2505", "DCE", "10:00:00", "20250501",
        -1.0, -100.5, 0.0, 0, 0, 0,
        0.0, 0.0, 0.0, -999.99,
        -50.0, -1.0, -999.0, -0.001, 0);

    auto payload = build_payload_from_tick(tick);

    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["last_price"]),  -1.0);
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["bid_price1"]), -100.5);
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["ask_price1"]),  0.0);
    EXPECT_DOUBLE_EQ(std::any_cast<double>(payload["lower_limit"]), -999.99);

    auto old_bytes = old_path_wire("shm_neg_old", "send_compute_greeks",
                                    "ctp_gateway_cpp_test", payload);
    auto new_bytes = new_path_wire("shm_neg_new", "ctp_gateway_cpp_test", tick);

    ASSERT_EQ(old_bytes.size(), new_bytes.size());
    EXPECT_EQ(old_bytes, new_bytes);
}

// ═══════════════════════════════════════════════════════════════════════
// Layer 4: Wire header format validation
// ═══════════════════════════════════════════════════════════════════════

TEST(ShmWireFormatNamedTest, WireHeaderContainsCorrectTopic) {
    auto tick    = make_basic_tick();
    auto payload = build_payload_from_tick(tick);

    auto wire = new_path_wire("shm_hdr_test", "ctp_gateway_cpp_test", tick);
    ASSERT_GE(wire.size(), 2u + 19u); // 2 byte header + "send_compute_greeks" (19 chars)

    // Verify topic_len (little-endian uint16_t)
    uint16_t topic_len = static_cast<uint16_t>(wire[0])
                       | (static_cast<uint16_t>(wire[1]) << 8);
    EXPECT_EQ(topic_len, 19u); // strlen("send_compute_greeks")

    // Verify topic bytes
    std::string topic(reinterpret_cast<const char*>(wire.data() + 2), topic_len);
    EXPECT_EQ(topic, "send_compute_greeks");

    // Verify msgpack payload starts after header + topic
    auto msg_bytes = tyche::deserialize(wire.data() + 2 + topic_len,
                                         wire.size() - 2 - topic_len);
    EXPECT_EQ(msg_bytes.msg_type, tyche::MessageType::EVENT);
    EXPECT_EQ(msg_bytes.sender,   "ctp_gateway_cpp_test");
    EXPECT_EQ(msg_bytes.event,    "send_compute_greeks");

    // Spot-check a payload field
    auto& pl = msg_bytes.payload;
    EXPECT_EQ(std::any_cast<std::string>(pl["instrument_id"]), "ag2501C5000");
    EXPECT_DOUBLE_EQ(std::any_cast<double>(pl["last_price"]), 5000.0);
}

}  // namespace
