// Unit tests for tyche::SharedMemoryQueue - Cross-platform shared memory queue.

#include <gtest/gtest.h>

#include <thread>
#include <vector>

#include "tyche/cpp/engine/shared_memory_queue.h"

namespace tyche {
namespace {

// ── Construction ──────────────────────────────────────────────────────

TEST(SharedMemoryQueueTest, CreateAndDestroy) {
    {
        SharedMemoryQueue q({"test_create_destroy", 64, 1024}, true);
        EXPECT_TRUE(q.is_valid());
    }
    // After destruction (as owner), the queue should be cleaned up.
    // Opening as non-owner should fail because the owner unlinked it.
    {
        SharedMemoryQueue q({"test_create_destroy", 64, 1024}, false);
        // On Linux: shm_unlink removed it, so open fails.
        // On Windows: last handle closed, so open fails.
        EXPECT_FALSE(q.is_valid());
    }
}

TEST(SharedMemoryQueueTest, OwnerCreatesValidQueue) {
    SharedMemoryQueue q({"test_owner_valid", 128, 4096}, true);
    EXPECT_TRUE(q.is_valid());
    EXPECT_EQ(q.capacity(), 128u);
    EXPECT_TRUE(q.empty());
    EXPECT_EQ(q.size(), 0u);
}

TEST(SharedMemoryQueueTest, InvalidConfigRejectsLargeMessage) {
    SharedMemoryQueue q({"test_large_msg", 16, 32}, true);
    EXPECT_TRUE(q.is_valid());

    std::vector<uint8_t> data(33, 0xAB);
    EXPECT_FALSE(q.write(data));
}

// ── Basic Write/Read ──────────────────────────────────────────────────

TEST(SharedMemoryQueueTest, WriteAndRead) {
    SharedMemoryQueue q({"test_write_read", 64, 1024}, true);
    ASSERT_TRUE(q.is_valid());

    std::vector<uint8_t> data = {'h', 'e', 'l', 'l', 'o'};
    EXPECT_TRUE(q.write(data));
    EXPECT_EQ(q.size(), 1u);
    EXPECT_FALSE(q.empty());

    auto result = q.read();
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result.value(), data);
    EXPECT_TRUE(q.empty());
}

TEST(SharedMemoryQueueTest, ReadFromEmptyReturnsNullopt) {
    SharedMemoryQueue q({"test_read_empty", 64, 1024}, true);
    ASSERT_TRUE(q.is_valid());

    auto result = q.read();
    EXPECT_FALSE(result.has_value());
}

// ── FIFO Order ────────────────────────────────────────────────────────

TEST(SharedMemoryQueueTest, FIFOMultipleMessages) {
    SharedMemoryQueue q({"test_fifo", 64, 1024}, true);
    ASSERT_TRUE(q.is_valid());

    for (int i = 0; i < 20; ++i) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
        EXPECT_TRUE(q.write(data));
    }
    EXPECT_EQ(q.size(), 20u);

    for (int i = 0; i < 20; ++i) {
        auto result = q.read();
        ASSERT_TRUE(result.has_value());
        ASSERT_EQ(result.value().size(), 1u);
        EXPECT_EQ(result.value()[0], static_cast<uint8_t>(i));
    }
    EXPECT_TRUE(q.empty());
}

// ── Queue Full Behavior ───────────────────────────────────────────────

TEST(SharedMemoryQueueTest, WriteRejectsWhenFull) {
    SharedMemoryQueue q({"test_full", 4, 64}, true);
    ASSERT_TRUE(q.is_valid());

    // Fill queue
    for (int i = 0; i < 4; ++i) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
        EXPECT_TRUE(q.write(data));
    }
    EXPECT_EQ(q.size(), 4u);

    // Next write should fail (DROP_NEWEST semantics)
    std::vector<uint8_t> overflow = {0xFF};
    EXPECT_FALSE(q.write(overflow));
}

// ── Cross-process / Multi-thread Communication ────────────────────────

TEST(SharedMemoryQueueTest, ProducerConsumerThreads) {
    const char* queue_name = "test_producer_consumer";
    const int msg_count = 1000;

    {
        SharedMemoryQueue q_owner({queue_name, 1024, 256}, true);
        ASSERT_TRUE(q_owner.is_valid());

        std::thread producer([&q_owner, msg_count]() {
            for (int i = 0; i < msg_count; ++i) {
                std::vector<uint8_t> data(4);
                data[0] = static_cast<uint8_t>((i >> 0) & 0xFF);
                data[1] = static_cast<uint8_t>((i >> 8) & 0xFF);
                data[2] = static_cast<uint8_t>((i >> 16) & 0xFF);
                data[3] = static_cast<uint8_t>((i >> 24) & 0xFF);
                // Retry on full
                while (!q_owner.write(data)) {
                    std::this_thread::yield();
                }
            }
        });

        std::thread consumer([queue_name, msg_count]() {
            SharedMemoryQueue q_client({queue_name, 1024, 256}, false);
            ASSERT_TRUE(q_client.is_valid());

            int received = 0;
            while (received < msg_count) {
                auto result = q_client.read();
                if (result.has_value()) {
                    ASSERT_EQ(result.value().size(), 4u);
                    int value = result.value()[0] |
                               (result.value()[1] << 8) |
                               (result.value()[2] << 16) |
                               (result.value()[3] << 24);
                    EXPECT_EQ(value, received);
                    ++received;
                } else {
                    std::this_thread::yield();
                }
            }
        });

        producer.join();
        consumer.join();
    }
}

// ── Large Messages ────────────────────────────────────────────────────

TEST(SharedMemoryQueueTest, LargeMessageRoundTrip) {
    SharedMemoryQueue q({"test_large_msg", 16, 65536}, true);
    ASSERT_TRUE(q.is_valid());

    std::vector<uint8_t> large_data(60000);
    for (size_t i = 0; i < large_data.size(); ++i) {
        large_data[i] = static_cast<uint8_t>(i & 0xFF);
    }

    EXPECT_TRUE(q.write(large_data));

    auto result = q.read();
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result.value().size(), large_data.size());
    EXPECT_EQ(result.value(), large_data);
}

}  // namespace
}  // namespace tyche
