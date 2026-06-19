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

// Helper to convert Frame back to string for assertions
std::string frame_to_str(const Frame& f) {
    return std::string(f.data(), f.data() + f.size());
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

    std::string content(result->frames[0].data(), result->frames[0].data() + result->frames[0].size());
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

TEST(TopicQueueTest, BlockProducerBlocksWhenFull) {
    constexpr size_t CAP = 4;
    TopicQueue q(CAP, BackpressureStrategy::BLOCK_PRODUCER);

    // Fill the queue
    for (size_t i = 0; i < CAP; ++i) {
        EXPECT_TRUE(q.put(make_item(static_cast<double>(i), "item")));
    }
    EXPECT_EQ(q.size(), CAP);

    // Consumer thread: drain one item after a short delay
    std::thread consumer([&q] {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        auto item = q.get();
        ASSERT_TRUE(item.has_value());
    });

    // Producer thread: this should block until consumer makes room
    std::thread producer([&q] {
        EXPECT_TRUE(q.put(make_item(99.0, "blocked_item")));
    });

    producer.join();
    consumer.join();

    // Queue should still be full (CAP items)
    EXPECT_EQ(q.size(), CAP);
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
    EXPECT_EQ(frame_to_str(result->frames[0]), "topic");
    EXPECT_EQ(frame_to_str(result->frames[1]), "payload");
}

// ── Frame SSO / Heap Boundary ───────────────────────────────────────────

TEST(TopicQueueTest, FrameSSOAndHeap) {
    // Small frame (<=64 bytes) uses SSO
    std::vector<uint8_t> small_data(64, 'x');
    Frame small(small_data.data(), small_data.size());
    EXPECT_EQ(small.size(), 64u);
    EXPECT_FALSE(small.empty());

    // Large frame (>64 bytes) uses heap
    std::vector<uint8_t> large_data(128, 'y');
    Frame large(large_data.data(), large_data.size());
    EXPECT_EQ(large.size(), 128u);
    EXPECT_FALSE(large.empty());

    // Empty frame
    Frame empty(nullptr, 0);
    EXPECT_EQ(empty.size(), 0u);
    EXPECT_TRUE(empty.empty());
}

TEST(TopicQueueTest, FrameCopyAndMove) {
    std::vector<uint8_t> data(100, 'z');
    Frame original(data.data(), data.size());

    // Copy constructor
    Frame copied(original);
    EXPECT_EQ(copied.size(), original.size());
    EXPECT_EQ(copied, original);

    // Copy assignment
    Frame assigned = original;
    EXPECT_EQ(assigned.size(), original.size());
    EXPECT_EQ(assigned, original);

    // Move constructor
    Frame moved_from(original);
    Frame moved(std::move(moved_from));
    EXPECT_EQ(moved.size(), original.size());
    EXPECT_EQ(moved, original);
    EXPECT_TRUE(moved_from.empty());

    // Move assignment
    Frame move_assigned = std::move(copied);
    EXPECT_EQ(move_assigned.size(), original.size());
    EXPECT_EQ(move_assigned, original);
    EXPECT_TRUE(copied.empty());

    // Inequality
    std::vector<uint8_t> other_data(100, 'a');
    Frame other(other_data.data(), other_data.size());
    EXPECT_NE(original, other);
}

TEST(TopicQueueTest, FrameToVector) {
    std::vector<uint8_t> data = {'h', 'e', 'l', 'l', 'o'};
    Frame f(data.data(), data.size());
    auto vec = f.to_vector();
    EXPECT_EQ(vec, data);
}

// ── QueueItem Backward-Compatible Constructor ───────────────────────────

TEST(TopicQueueTest, QueueItemFromVectorOfVectors) {
    std::vector<std::vector<uint8_t>> frames = {
        {'f', 'r', 'a', 'm', 'e', '1'},
        {'f', 'r', 'a', 'm', 'e', '2'}
    };
    QueueItem item(3.14, frames);
    EXPECT_DOUBLE_EQ(item.enqueue_time, 3.14);
    ASSERT_EQ(item.frames.size(), 2u);
    EXPECT_EQ(frame_to_str(item.frames[0]), "frame1");
    EXPECT_EQ(frame_to_str(item.frames[1]), "frame2");
}

// ── DROP_OLDEST Multiple Overwrites ───────────────────────────────────

TEST(TopicQueueTest, DropOldestMultipleOverwrites) {
    constexpr size_t CAP = 4;
    TopicQueue q(CAP, BackpressureStrategy::DROP_OLDEST);

    // Fill
    for (size_t i = 0; i < CAP; ++i) {
        EXPECT_TRUE(q.put(make_item(static_cast<double>(i), "item" + std::to_string(i))));
    }

    // Overwrite all items one by one
    for (size_t i = CAP; i < CAP + CAP; ++i) {
        EXPECT_TRUE(q.put(make_item(static_cast<double>(i), "new" + std::to_string(i))));
    }

    // Pop all - should only see the newest CAP items
    for (size_t i = CAP; i < CAP + CAP; ++i) {
        auto result = q.get();
        ASSERT_TRUE(result.has_value());
        EXPECT_DOUBLE_EQ(result->enqueue_time, static_cast<double>(i));
    }
    EXPECT_TRUE(q.empty());
}

// ── Concurrent Producer/Consumer ────────────────────────────────────────

TEST(TopicQueueTest, ConcurrentPutGet) {
    TopicQueue q(64);
    constexpr int NUM_ITEMS = 100;

    std::thread producer([&q, NUM_ITEMS] {
        for (int i = 0; i < NUM_ITEMS; ++i) {
            q.put(make_item(static_cast<double>(i), std::to_string(i)));
        }
    });

    int count = 0;
    while (count < NUM_ITEMS) {
        auto result = q.get();
        if (result.has_value()) {
            ++count;
        } else {
            std::this_thread::yield();
        }
    }

    producer.join();
    EXPECT_EQ(count, NUM_ITEMS);
    EXPECT_EQ(q.processed(), static_cast<uint64_t>(NUM_ITEMS));
}

// ── Empty Queue Operations ────────────────────────────────────────────

TEST(TopicQueueTest, EmptyQueueStats) {
    TopicQueue q(8);
    EXPECT_TRUE(q.empty());
    EXPECT_EQ(q.size(), 0u);
    EXPECT_EQ(q.processed(), 0u);
    EXPECT_EQ(q.dropped(), 0u);

    // Get from empty should not increment processed
    auto result = q.get();
    EXPECT_FALSE(result.has_value());
    EXPECT_EQ(q.processed(), 0u);
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
