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

}  // namespace
}  // namespace tyche
