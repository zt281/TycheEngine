// Unit tests for tyche::TopicQueue - Topic queue with backpressure strategies.

#include <gtest/gtest.h>

#include <vector>

#include "tyche/cpp/engine/topic_queue.h"

namespace tyche {
namespace {

// Helper to create a QueueItem
QueueItem make_item(double t, const std::string& content) {
    std::vector<uint8_t> frame(content.begin(), content.end());
    return QueueItem(t, {frame});
}

// ── Construction ──────────────────────────────────────────────────────

TEST(TopicQueueTest, DefaultConstruction) {
    TopicQueue q;
    EXPECT_TRUE(q.empty());
    EXPECT_EQ(q.size(), 0u);
    EXPECT_EQ(q.processed(), 0u);
    EXPECT_EQ(q.dropped(), 0u);
    EXPECT_EQ(q.strategy(), BackpressureStrategy::DROP_OLDEST);
}

TEST(TopicQueueTest, CustomCapacityAndStrategy) {
    TopicQueue q(128, BackpressureStrategy::DROP_NEWEST);
    EXPECT_EQ(q.capacity(), 128u);
    EXPECT_EQ(q.strategy(), BackpressureStrategy::DROP_NEWEST);
}

// ── Basic Put/Get ─────────────────────────────────────────────────────

TEST(TopicQueueTest, PutAndGet) {
    TopicQueue q(8);
    auto item = make_item(1.0, "test_event");
    EXPECT_TRUE(q.put(std::move(item)));
    EXPECT_EQ(q.size(), 1u);

    auto result = q.get();
    ASSERT_TRUE(result.has_value());
    EXPECT_DOUBLE_EQ(result->enqueue_time, 1.0);
    EXPECT_EQ(result->frames.size(), 1u);

    std::string content(result->frames[0].begin(), result->frames[0].end());
    EXPECT_EQ(content, "test_event");
}

TEST(TopicQueueTest, GetFromEmptyReturnsNullopt) {
    TopicQueue q(4);
    auto result = q.get();
    EXPECT_FALSE(result.has_value());
}

TEST(TopicQueueTest, ProcessedCountIncrementsOnGet) {
    TopicQueue q(8);
    q.put(make_item(1.0, "a"));
    q.put(make_item(2.0, "b"));

    EXPECT_EQ(q.processed(), 0u);
    q.get();
    EXPECT_EQ(q.processed(), 1u);
    q.get();
    EXPECT_EQ(q.processed(), 2u);
}

// ── DROP_OLDEST Strategy ──────────────────────────────────────────────

TEST(TopicQueueTest, DropOldestOverwritesWhenFull) {
    TopicQueue q(4, BackpressureStrategy::DROP_OLDEST);

    // Fill queue
    for (int i = 0; i < 4; ++i) {
        EXPECT_TRUE(q.put(make_item(static_cast<double>(i), "item_" + std::to_string(i))));
    }
    EXPECT_EQ(q.size(), 4u);

    // Push one more - should overwrite oldest
    EXPECT_TRUE(q.put(make_item(99.0, "new_item")));

    // First pop should NOT be item_0 (it was overwritten)
    auto result = q.get();
    ASSERT_TRUE(result.has_value());
    // The oldest was discarded to make room
    EXPECT_GE(result->enqueue_time, 1.0);
}

// ── DROP_NEWEST Strategy ──────────────────────────────────────────────

TEST(TopicQueueTest, DropNewestRejectWhenFull) {
    TopicQueue q(4, BackpressureStrategy::DROP_NEWEST);

    // Fill queue
    for (int i = 0; i < 4; ++i) {
        EXPECT_TRUE(q.put(make_item(static_cast<double>(i), "item")));
    }

    // New push should be rejected
    EXPECT_FALSE(q.put(make_item(99.0, "rejected")));
    EXPECT_EQ(q.dropped(), 1u);
    EXPECT_EQ(q.size(), 4u);

    // Original items preserved
    auto result = q.get();
    ASSERT_TRUE(result.has_value());
    EXPECT_DOUBLE_EQ(result->enqueue_time, 0.0);
}

TEST(TopicQueueTest, DropNewestCountsMultipleDrops) {
    TopicQueue q(2, BackpressureStrategy::DROP_NEWEST);

    q.put(make_item(1.0, "a"));
    q.put(make_item(2.0, "b"));

    // Both should fail
    EXPECT_FALSE(q.put(make_item(3.0, "c")));
    EXPECT_FALSE(q.put(make_item(4.0, "d")));
    EXPECT_EQ(q.dropped(), 2u);
}

// ── BLOCK_PRODUCER Strategy ───────────────────────────────────────────

TEST(TopicQueueTest, BlockProducerAlwaysReturnsTrue) {
    TopicQueue q(8, BackpressureStrategy::BLOCK_PRODUCER);

    // Non-full case: immediate success
    EXPECT_TRUE(q.put(make_item(1.0, "test")));
    EXPECT_EQ(q.size(), 1u);
}

// ── Multi-frame Items ─────────────────────────────────────────────────

TEST(TopicQueueTest, MultiFrameItems) {
    TopicQueue q(8);

    std::vector<std::vector<uint8_t>> frames = {
        {'t', 'o', 'p', 'i', 'c'},
        {'p', 'a', 'y', 'l', 'o', 'a', 'd'}
    };
    QueueItem item(1.5, frames);
    q.put(std::move(item));

    auto result = q.get();
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->frames.size(), 2u);
    EXPECT_EQ(std::string(result->frames[0].begin(), result->frames[0].end()), "topic");
    EXPECT_EQ(std::string(result->frames[1].begin(), result->frames[1].end()), "payload");
}

// ── FIFO Order ────────────────────────────────────────────────────────

TEST(TopicQueueTest, FIFOOrder) {
    TopicQueue q(16);

    for (int i = 0; i < 10; ++i) {
        q.put(make_item(static_cast<double>(i), std::to_string(i)));
    }

    for (int i = 0; i < 10; ++i) {
        auto result = q.get();
        ASSERT_TRUE(result.has_value());
        EXPECT_DOUBLE_EQ(result->enqueue_time, static_cast<double>(i));
    }
}

}  // namespace
}  // namespace tyche
