// Unit tests for tyche::DeadLetterStore - JSONL dead letter persistence.

#include <gtest/gtest.h>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "tyche/cpp/engine/dead_letter_store.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

namespace tyche {
namespace {

namespace fs = std::filesystem;

// Test fixture that creates and cleans up a temporary directory
class DeadLetterStoreTest : public ::testing::Test {
protected:
    std::string test_dir;

    void SetUp() override {
        test_dir = (fs::temp_directory_path() / "tyche_test_dead_letters").string();
        // Clean up any previous test run
        fs::remove_all(test_dir);
    }

    void TearDown() override {
        fs::remove_all(test_dir);
    }

    Message make_test_message(const std::string& event, const std::string& sender = "test_mod") {
        Message msg;
        msg.msg_type = MessageType::EVENT;
        msg.sender = sender;
        msg.event = event;
        msg.payload["key"] = std::string("value");
        msg.durability = DurabilityLevel::ASYNC_FLUSH;
        return msg;
    }
};

// ── Construction ──────────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, Construction) {
    DeadLetterStore store(test_dir);
    EXPECT_EQ(store.data_dir(), test_dir);
}

// ── Persist ───────────────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, PersistCreatesDirectory) {
    DeadLetterStore store(test_dir);
    auto msg = make_test_message("test_event");

    store.persist(msg, "test_topic", "wait_timeout");

    EXPECT_TRUE(fs::exists(test_dir));
    EXPECT_TRUE(fs::is_directory(test_dir));
}

TEST_F(DeadLetterStoreTest, PersistCreatesFile) {
    DeadLetterStore store(test_dir);
    auto msg = make_test_message("test_event");

    store.persist(msg, "tick", "broadcast_ttl_expired");

    // Should have at least one .jsonl file
    bool found_jsonl = false;
    for (const auto& entry : fs::directory_iterator(test_dir)) {
        if (entry.path().extension() == ".jsonl") {
            found_jsonl = true;
            break;
        }
    }
    EXPECT_TRUE(found_jsonl);
}

TEST_F(DeadLetterStoreTest, PersistWritesValidJsonl) {
    DeadLetterStore store(test_dir);
    auto msg = make_test_message("price_update");

    store.persist(msg, "tick", "run_timeout");

    // Read the file and verify content
    for (const auto& entry : fs::directory_iterator(test_dir)) {
        if (entry.path().extension() == ".jsonl") {
            std::ifstream file(entry.path());
            std::string line;
            ASSERT_TRUE(std::getline(file, line));
            EXPECT_FALSE(line.empty());

            // Should contain expected fields
            EXPECT_NE(line.find("\"topic\""), std::string::npos);
            EXPECT_NE(line.find("\"tick\""), std::string::npos);
            EXPECT_NE(line.find("\"reason\""), std::string::npos);
            EXPECT_NE(line.find("\"run_timeout\""), std::string::npos);
            EXPECT_NE(line.find("\"message\""), std::string::npos);
            EXPECT_NE(line.find("\"timestamp\""), std::string::npos);
            break;
        }
    }
}

TEST_F(DeadLetterStoreTest, PersistMultipleRecords) {
    DeadLetterStore store(test_dir);

    for (int i = 0; i < 5; ++i) {
        auto msg = make_test_message("event_" + std::to_string(i));
        store.persist(msg, "topic_" + std::to_string(i), "wait_timeout");
    }

    // Count lines in the file
    int line_count = 0;
    for (const auto& entry : fs::directory_iterator(test_dir)) {
        if (entry.path().extension() == ".jsonl") {
            std::ifstream file(entry.path());
            std::string line;
            while (std::getline(file, line)) {
                if (!line.empty()) ++line_count;
            }
        }
    }
    EXPECT_EQ(line_count, 5);
}

// ── Replay ────────────────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, ReplayEmptyStore) {
    DeadLetterStore store(test_dir);
    auto results = store.replay();
    EXPECT_TRUE(results.empty());
}

TEST_F(DeadLetterStoreTest, ReplayAfterPersist) {
    DeadLetterStore store(test_dir);
    auto msg = make_test_message("query_price");
    store.persist(msg, "price_topic", "wait_timeout");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("price_topic"), std::string::npos);
}

TEST_F(DeadLetterStoreTest, ReplayWithTopicFilter) {
    DeadLetterStore store(test_dir);

    store.persist(make_test_message("e1"), "tick", "timeout");
    store.persist(make_test_message("e2"), "quote", "timeout");
    store.persist(make_test_message("e3"), "tick", "expired");

    // Filter by "tick"
    auto results = store.replay(std::string("tick"));
    EXPECT_EQ(results.size(), 2u);

    // Filter by "quote"
    results = store.replay(std::string("quote"));
    EXPECT_EQ(results.size(), 1u);

    // Filter by nonexistent topic
    results = store.replay(std::string("nonexistent"));
    EXPECT_EQ(results.size(), 0u);
}

TEST_F(DeadLetterStoreTest, ReplayWithMaxCount) {
    DeadLetterStore store(test_dir);

    for (int i = 0; i < 10; ++i) {
        store.persist(make_test_message("e" + std::to_string(i)), "topic", "timeout");
    }

    auto results = store.replay(std::nullopt, std::nullopt, 3);
    EXPECT_EQ(results.size(), 3u);
}

// ── Message Content in Dead Letter ────────────────────────────────────

TEST_F(DeadLetterStoreTest, MessageFieldsSerialized) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::REQUEST;
    msg.sender = "greeks_engine_a1b2c3";
    msg.event = "compute_greeks";
    msg.payload["instrument"] = std::string("IO2506-C-4000");
    msg.payload["price"] = 3.14;
    msg.correlation_id = "corr-id-123";
    msg.recipient = "target_mod";
    msg.wait_timeout = 5.0f;
    msg.run_timeout = 30.0f;

    store.persist(msg, "compute_greeks", "run_timeout");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);

    const auto& record = results[0];
    EXPECT_NE(record.find("greeks_engine_a1b2c3"), std::string::npos);
    EXPECT_NE(record.find("compute_greeks"), std::string::npos);
    EXPECT_NE(record.find("IO2506-C-4000"), std::string::npos);
    EXPECT_NE(record.find("corr-id-123"), std::string::npos);
}

// ── Thread Safety ─────────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, ConcurrentPersist) {
    DeadLetterStore store(test_dir);
    constexpr int NUM_THREADS = 4;
    constexpr int WRITES_PER_THREAD = 25;

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&store, t, WRITES_PER_THREAD] {
            for (int i = 0; i < WRITES_PER_THREAD; ++i) {
                auto msg = Message{};
                msg.msg_type = MessageType::EVENT;
                msg.sender = "thread_" + std::to_string(t);
                msg.event = "evt_" + std::to_string(i);
                store.persist(msg, "topic_" + std::to_string(t), "timeout");
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    auto results = store.replay(std::nullopt, std::nullopt, 200);
    EXPECT_EQ(results.size(), static_cast<size_t>(NUM_THREADS * WRITES_PER_THREAD));
}

// ── Special Characters ────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, SpecialCharactersInPayload) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "mod_a";
    msg.event = "test";
    msg.payload["data"] = std::string("line1\nline2\ttab\"quote\\backslash");

    store.persist(msg, "special_topic", "error");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    // Should be valid JSON (properly escaped)
    EXPECT_NE(results[0].find("\\n"), std::string::npos);
    EXPECT_NE(results[0].find("\\t"), std::string::npos);
}

// ── any_to_json Type Coverage ───────────────────────────────────────────

TEST_F(DeadLetterStoreTest, AllAnyTypesInPayload) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "type_test";
    msg.event = "all_types";

    // Cover various any_to_json branches
    msg.payload["str"] = std::string("hello");
    msg.payload["cstr"] = "const_char_star";
    msg.payload["bool_t"] = true;
    msg.payload["bool_f"] = false;
    msg.payload["int"] = 42;
    msg.payload["int64"] = int64_t{-9007199254740992LL};
    msg.payload["uint64"] = uint64_t{18446744073709551615ULL};
    msg.payload["uint"] = unsigned int{99};
    msg.payload["long_v"] = long{-123456789L};
    msg.payload["ulong_v"] = uint64_t{9876543210UL};
    msg.payload["double"] = 3.141592653589793;
    msg.payload["float"] = 2.7182818f;
    msg.payload["empty_any"] = std::any{};

    // Nested Payload map
    Payload nested;
    nested["inner_key"] = std::string("inner_value");
    msg.payload["nested"] = nested;

    // Vector of std::any
    std::vector<std::any> vec;
    vec.push_back(std::string("vec_str"));
    vec.push_back(123);
    vec.push_back(4.56);
    msg.payload["vec_any"] = vec;

    store.persist(msg, "type_topic", "test");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    const auto& r = results[0];

    EXPECT_NE(r.find("\"str\": \"hello\""), std::string::npos);
    EXPECT_NE(r.find("\"cstr\": \"const_char_star\""), std::string::npos);
    EXPECT_NE(r.find("\"bool_t\": true"), std::string::npos);
    EXPECT_NE(r.find("\"bool_f\": false"), std::string::npos);
    EXPECT_NE(r.find("\"int\": 42"), std::string::npos);
    EXPECT_NE(r.find("\"int64\": -9007199254740992"), std::string::npos);
    EXPECT_NE(r.find("\"uint64\": 18446744073709551615"), std::string::npos);
    EXPECT_NE(r.find("\"uint\": 99"), std::string::npos);
    EXPECT_NE(r.find("\"long_v\": -123456789"), std::string::npos);
    EXPECT_NE(r.find("\"ulong_v\": 9876543210"), std::string::npos);
    EXPECT_NE(r.find("\"float\": 2.718281"), std::string::npos);
    EXPECT_NE(r.find("\"empty_any\": null"), std::string::npos);
    EXPECT_NE(r.find("\"inner_key\": \"inner_value\""), std::string::npos);
    EXPECT_NE(r.find("\"vec_any\": [\"vec_str\", 123, 4.5"), std::string::npos);
}

TEST_F(DeadLetterStoreTest, EmptyPayload) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "empty_sender";
    msg.event = "empty_event";
    // payload is empty

    store.persist(msg, "empty_topic", "reason");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("\"payload\": {}"), std::string::npos);
}

TEST_F(DeadLetterStoreTest, NaNAndInfValues) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "nan_sender";
    msg.event = "nan_event";
    msg.payload["nan_double"] = std::numeric_limits<double>::quiet_NaN();
    msg.payload["inf_double"] = std::numeric_limits<double>::infinity();
    msg.payload["nan_float"] = std::numeric_limits<float>::quiet_NaN();
    msg.payload["inf_float"] = std::numeric_limits<float>::infinity();

    store.persist(msg, "nan_topic", "reason");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("\"nan_double\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"inf_double\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"nan_float\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"inf_float\": null"), std::string::npos);
}

TEST_F(DeadLetterStoreTest, EscapeJsonControlCharacters) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::EVENT;
    msg.sender = "ctrl";
    msg.event = "ctrl_event";
    msg.payload["carriage"] = std::string("a\rb");
    msg.payload["backspace"] = std::string("a\bb");
    msg.payload["formfeed"] = std::string("a\fb");
    msg.payload["null_char"] = std::string("a\0b", 3);

    store.persist(msg, "ctrl_topic", "reason");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("\\r"), std::string::npos);
    EXPECT_NE(results[0].find("\\b"), std::string::npos);
    EXPECT_NE(results[0].find("\\f"), std::string::npos);
    EXPECT_NE(results[0].find("\\u0000"), std::string::npos);
}

// ── Replay Filters ──────────────────────────────────────────────────────

TEST_F(DeadLetterStoreTest, ReplayWithSinceDate) {
    DeadLetterStore store(test_dir);

    // Persist a message
    store.persist(make_test_message("evt1"), "topic", "timeout");

    // Replay with a future since_date should return nothing
    auto results = store.replay(std::nullopt, std::string("2099-01-01"), 100);
    EXPECT_EQ(results.size(), 0u);

    // Replay with a past since_date should return the record
    results = store.replay(std::nullopt, std::string("2000-01-01"), 100);
    EXPECT_EQ(results.size(), 1u);
}

TEST_F(DeadLetterStoreTest, ReplayMaxCountZero) {
    DeadLetterStore store(test_dir);

    for (int i = 0; i < 5; ++i) {
        store.persist(make_test_message("e" + std::to_string(i)), "topic", "timeout");
    }

    auto results = store.replay(std::nullopt, std::nullopt, 0);
    EXPECT_EQ(results.size(), 0u);
}

// ── Optional Fields Serialization ───────────────────────────────────────

TEST_F(DeadLetterStoreTest, OptionalFieldsNullWhenUnset) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::REQUEST;
    msg.sender = "sender";
    msg.event = "event";
    msg.payload["k"] = std::string("v");
    // recipient, timestamp, correlation_id, wait_timeout, run_timeout all unset

    store.persist(msg, "opt_topic", "reason");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("\"recipient\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"timestamp\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"correlation_id\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"wait_timeout\": null"), std::string::npos);
    EXPECT_NE(results[0].find("\"run_timeout\": null"), std::string::npos);
}

TEST_F(DeadLetterStoreTest, OptionalFieldsSet) {
    DeadLetterStore store(test_dir);

    Message msg;
    msg.msg_type = MessageType::REQUEST;
    msg.sender = "sender";
    msg.event = "event";
    msg.payload["k"] = std::string("v");
    msg.recipient = "target";
    msg.timestamp = 12345.67;
    msg.correlation_id = "corr-abc";
    msg.wait_timeout = 5.0f;
    msg.run_timeout = 30.0f;

    store.persist(msg, "opt_topic", "reason");

    auto results = store.replay();
    ASSERT_EQ(results.size(), 1u);
    EXPECT_NE(results[0].find("\"recipient\": \"target\""), std::string::npos);
    EXPECT_NE(results[0].find("\"timestamp\": 12345.67"), std::string::npos);
    EXPECT_NE(results[0].find("\"correlation_id\": \"corr-abc\""), std::string::npos);
    EXPECT_NE(results[0].find("\"wait_timeout\": 5"), std::string::npos);
    EXPECT_NE(results[0].find("\"run_timeout\": 30"), std::string::npos);
}

// ── Persist Error Paths (best-effort) ─────────────────────────────────

TEST_F(DeadLetterStoreTest, PersistWithInvalidDirectory) {
    // Use a path that is likely invalid on all platforms (null byte in path)
    // On Windows this may still succeed depending on API, so we just verify
    // it does not crash.  We cannot easily force a real failure without mocking
    // the filesystem, but we exercise the catch paths by using an extremely
    // long path on Windows or a read-only parent on Unix.
#ifdef _WIN32
    std::string bad_dir = std::string(512, 'A') + "/dlq";
#else
    std::string bad_dir = "/dev/null/dlq";
#endif

    DeadLetterStore store(bad_dir);
    auto msg = make_test_message("evt");

    // Should not throw
    EXPECT_NO_THROW(store.persist(msg, "topic", "reason"));
}

}  // namespace
}  // namespace tyche
