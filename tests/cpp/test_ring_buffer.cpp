// Unit tests for tyche::RingBuffer - Lock-free MPSC ring buffer.

#include <gtest/gtest.h>

#include <algorithm>
#include <atomic>
#include <thread>
#include <vector>

#include "tyche/cpp/engine/ring_buffer.h"

namespace tyche {
namespace {

// ── Basic Construction ────────────────────────────────────────────────

TEST(RingBufferTest, CapacityRoundsUpToPowerOf2) {
    RingBuffer<int> rb(5);
    EXPECT_EQ(rb.capacity(), 8u);  // next power of 2 >= 5

    RingBuffer<int> rb2(16);
    EXPECT_EQ(rb2.capacity(), 16u);  // already power of 2

    RingBuffer<int> rb3(1);
    EXPECT_EQ(rb3.capacity(), 2u);  // minimum capacity is 2
}

TEST(RingBufferTest, InitiallyEmpty) {
    RingBuffer<int> rb(8);
    EXPECT_TRUE(rb.empty());
    EXPECT_FALSE(rb.full());
    EXPECT_EQ(rb.size(), 0u);
}

// ── Basic Push/Pop ────────────────────────────────────────────────────

TEST(RingBufferTest, PushAndPopSingleItem) {
    RingBuffer<int> rb(4);
    EXPECT_TRUE(rb.try_push(42));
    EXPECT_EQ(rb.size(), 1u);
    EXPECT_FALSE(rb.empty());

    auto val = rb.pop();
    ASSERT_TRUE(val.has_value());
    EXPECT_EQ(*val, 42);
    EXPECT_TRUE(rb.empty());
}

TEST(RingBufferTest, PushAndPopMultipleItems) {
    RingBuffer<int> rb(8);
    for (int i = 0; i < 5; ++i) {
        EXPECT_TRUE(rb.try_push(i * 10));
    }
    EXPECT_EQ(rb.size(), 5u);

    for (int i = 0; i < 5; ++i) {
        auto val = rb.pop();
        ASSERT_TRUE(val.has_value());
        EXPECT_EQ(*val, i * 10);
    }
    EXPECT_TRUE(rb.empty());
}

TEST(RingBufferTest, PopFromEmptyReturnsNullopt) {
    RingBuffer<int> rb(4);
    auto val = rb.pop();
    EXPECT_FALSE(val.has_value());
}

// ── Full Buffer Behavior ──────────────────────────────────────────────

TEST(RingBufferTest, TryPushReturnsFalseWhenFull) {
    RingBuffer<int> rb(4);  // capacity = 4
    for (int i = 0; i < 4; ++i) {
        EXPECT_TRUE(rb.try_push(i));
    }
    EXPECT_TRUE(rb.full());

    // Should fail - buffer is full
    EXPECT_FALSE(rb.try_push(999));
    EXPECT_EQ(rb.size(), 4u);
}

TEST(RingBufferTest, PushAfterPopWorks) {
    RingBuffer<int> rb(4);
    // Fill completely
    for (int i = 0; i < 4; ++i) {
        rb.try_push(i);
    }
    // Pop one
    auto val = rb.pop();
    ASSERT_TRUE(val.has_value());
    EXPECT_EQ(*val, 0);

    // Should be able to push again
    EXPECT_TRUE(rb.try_push(99));
    EXPECT_EQ(rb.size(), 4u);
}

// ── push_overwrite (DROP_OLDEST) ──────────────────────────────────────

TEST(RingBufferTest, PushOverwriteDiscardsOldest) {
    RingBuffer<int> rb(4);  // capacity = 4
    for (int i = 0; i < 4; ++i) {
        rb.try_push(i);  // [0, 1, 2, 3]
    }
    EXPECT_TRUE(rb.full());

    // Overwrite - should discard item 0
    rb.push_overwrite(99);

    // Pop and verify: oldest (0) was discarded
    auto val = rb.pop();
    ASSERT_TRUE(val.has_value());
    EXPECT_EQ(*val, 1);  // 0 was overwritten
}

// ── push_blocking (BLOCK_PRODUCER) ────────────────────────────────────

TEST(RingBufferTest, PushBlockingEventuallySucceeds) {
    RingBuffer<int> rb(4);
    for (int i = 0; i < 4; ++i) {
        rb.try_push(i);
    }
    EXPECT_TRUE(rb.full());

    // Launch a consumer that will free space
    std::atomic<bool> done{false};
    std::thread consumer([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        rb.pop();
        done.store(true);
    });

    // This should block until consumer pops an item
    rb.push_blocking(42);

    consumer.join();
    EXPECT_TRUE(done.load());
}

// ── Move Semantics ────────────────────────────────────────────────────

TEST(RingBufferTest, MoveOnlyTypes) {
    RingBuffer<std::unique_ptr<int>> rb(4);

    auto ptr = std::make_unique<int>(42);
    EXPECT_TRUE(rb.try_push(std::move(ptr)));
    EXPECT_EQ(ptr, nullptr);  // moved

    auto result = rb.pop();
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(**result, 42);
}

// ── String Type ───────────────────────────────────────────────────────

TEST(RingBufferTest, StringItems) {
    RingBuffer<std::string> rb(8);
    rb.try_push(std::string("hello"));
    rb.try_push(std::string("world"));

    auto v1 = rb.pop();
    auto v2 = rb.pop();
    ASSERT_TRUE(v1.has_value());
    ASSERT_TRUE(v2.has_value());
    EXPECT_EQ(*v1, "hello");
    EXPECT_EQ(*v2, "world");
}

// ── Wrap-around ───────────────────────────────────────────────────────

TEST(RingBufferTest, WrapAround) {
    RingBuffer<int> rb(4);  // capacity = 4

    // Push and pop past capacity boundary
    for (int round = 0; round < 3; ++round) {
        for (int i = 0; i < 4; ++i) {
            EXPECT_TRUE(rb.try_push(round * 100 + i));
        }
        for (int i = 0; i < 4; ++i) {
            auto val = rb.pop();
            ASSERT_TRUE(val.has_value());
            EXPECT_EQ(*val, round * 100 + i);
        }
        EXPECT_TRUE(rb.empty());
    }
}

// ── Concurrent MPSC ───────────────────────────────────────────────────

TEST(RingBufferTest, MultiProducerSingleConsumer) {
    constexpr int NUM_PRODUCERS = 4;
    constexpr int ITEMS_PER_PRODUCER = 1000;
    constexpr int TOTAL_ITEMS = NUM_PRODUCERS * ITEMS_PER_PRODUCER;

    RingBuffer<int> rb(8192);  // large enough to hold all items

    std::atomic<int> push_count{0};
    std::vector<std::thread> producers;

    for (int p = 0; p < NUM_PRODUCERS; ++p) {
        producers.emplace_back([&rb, &push_count, p, ITEMS_PER_PRODUCER] {
            for (int i = 0; i < ITEMS_PER_PRODUCER; ++i) {
                int value = p * ITEMS_PER_PRODUCER + i;
                while (!rb.try_push(value)) {
                    std::this_thread::yield();
                }
                push_count.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }

    // Consumer: collect all items
    std::vector<int> consumed;
    consumed.reserve(TOTAL_ITEMS);

    while (static_cast<int>(consumed.size()) < TOTAL_ITEMS) {
        auto val = rb.pop();
        if (val.has_value()) {
            consumed.push_back(*val);
        } else {
            std::this_thread::yield();
        }
    }

    for (auto& t : producers) {
        t.join();
    }

    // Verify all items were received
    EXPECT_EQ(consumed.size(), static_cast<size_t>(TOTAL_ITEMS));

    // Verify all unique values present
    std::sort(consumed.begin(), consumed.end());
    for (int i = 0; i < TOTAL_ITEMS; ++i) {
        EXPECT_EQ(consumed[i], i);
    }
}

// ── Copy Push ─────────────────────────────────────────────────────────

TEST(RingBufferTest, CopyPush) {
    RingBuffer<std::string> rb(4);
    std::string hello = "hello_copy";
    EXPECT_TRUE(rb.try_push(hello));
    EXPECT_EQ(hello, "hello_copy");  // original unchanged

    auto val = rb.pop();
    ASSERT_TRUE(val.has_value());
    EXPECT_EQ(*val, "hello_copy");
}

}  // namespace
}  // namespace tyche
