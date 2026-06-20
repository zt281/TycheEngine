// Unit tests for tyche::TopicQueueIndex.
//
// Tests:
//   1. Get returns nullptr for unregistered ID
//   2. Set and get round-trip
//   3. Snapshot returns only non-null entries
//   4. Multiple sets with resize
//   5. Concurrent reads during write

#include <gtest/gtest.h>

#include "tyche/cpp/engine/topic_queue_index.h"
#include "tyche/cpp/engine/topic_queue.h"

#include <atomic>
#include <chrono>
#include <thread>
#include <vector>

namespace tyche {
namespace {

TEST(TopicQueueIndexTest, GetReturnsNullptrForUnregistered) {
    TopicQueueIndex index;

    EXPECT_EQ(index.get(1), nullptr);
    EXPECT_EQ(index.get(42), nullptr);
    EXPECT_EQ(index.get(999), nullptr);
}

TEST(TopicQueueIndexTest, SetAndGetRoundTrip) {
    TopicQueueIndex index;
    TopicQueue queue(100);

    index.set(1, &queue);
    EXPECT_EQ(index.get(1), &queue);

    index.set(2, &queue);
    EXPECT_EQ(index.get(2), &queue);
    EXPECT_EQ(index.get(1), &queue);  // Original still valid
}

TEST(TopicQueueIndexTest, SnapshotReturnsNonNullEntries) {
    TopicQueueIndex index;
    TopicQueue q1(100);
    TopicQueue q2(100);

    index.set(1, &q1);
    index.set(3, &q2);
    // ID 2 is intentionally left empty

    auto snap = index.snapshot();
    EXPECT_EQ(snap.size(), 2u);

    // Verify both entries are present
    bool found_q1 = false, found_q2 = false;
    for (auto& [id, q] : snap) {
        if (id == 1 && q == &q1) found_q1 = true;
        if (id == 3 && q == &q2) found_q2 = true;
    }
    EXPECT_TRUE(found_q1);
    EXPECT_TRUE(found_q2);
}

TEST(TopicQueueIndexTest, SnapshotEmptyWhenNothingRegistered) {
    TopicQueueIndex index;
    auto snap = index.snapshot();
    EXPECT_TRUE(snap.empty());
}

TEST(TopicQueueIndexTest, MultipleSetsWithResize) {
    TopicQueueIndex index;
    TopicQueue queue(100);

    // Set a large ID to trigger resize
    index.set(100, &queue);
    EXPECT_EQ(index.get(100), &queue);

    // Set smaller IDs
    index.set(50, &queue);
    index.set(75, &queue);
    EXPECT_EQ(index.get(50), &queue);
    EXPECT_EQ(index.get(75), &queue);
    EXPECT_EQ(index.get(100), &queue);

    auto snap = index.snapshot();
    EXPECT_EQ(snap.size(), 3u);
}

TEST(TopicQueueIndexTest, OverwriteExistingId) {
    TopicQueueIndex index;
    TopicQueue q1(100);
    TopicQueue q2(100);

    index.set(1, &q1);
    EXPECT_EQ(index.get(1), &q1);

    index.set(1, &q2);
    EXPECT_EQ(index.get(1), &q2);
}

TEST(TopicQueueIndexTest, ConcurrentReadsDuringWrite) {
    TopicQueueIndex index;
    TopicQueue queue(100);

    // Pre-register some entries
    for (int i = 1; i <= 50; ++i) {
        index.set(static_cast<InternId>(i), &queue);
    }

    std::atomic<bool> writers_done{false};
    std::atomic<int> read_errors{0};

    // Reader threads
    std::vector<std::thread> readers;
    for (int t = 0; t < 4; ++t) {
        readers.emplace_back([&]() {
            for (int round = 0; round < 1000; ++round) {
                for (int i = 1; i <= 50; ++i) {
                    TopicQueue* q = index.get(static_cast<InternId>(i));
                    if (q != &queue && q != nullptr) {
                        read_errors.fetch_add(1);
                    }
                }
                auto snap = index.snapshot();
                for (auto& [id, q] : snap) {
                    if (q != &queue) {
                        read_errors.fetch_add(1);
                    }
                }
            }
        });
    }

    // Writer thread: continuously add new entries
    std::thread writer([&]() {
        for (int i = 51; i <= 100; ++i) {
            index.set(static_cast<InternId>(i), &queue);
        }
        writers_done.store(true);
    });

    for (auto& t : readers) {
        t.join();
    }
    writer.join();

    EXPECT_EQ(read_errors.load(), 0);
    EXPECT_EQ(index.get(100), &queue);
}

TEST(TopicQueueIndexTest, GetIsLockFree) {
    TopicQueueIndex index;
    TopicQueue queue(100);
    index.set(1, &queue);

    // get() should be fast (lock-free read)
    constexpr int kSamples = 100000;
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < kSamples; ++i) {
        volatile TopicQueue* q = index.get(1);
        (void)q;
    }
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    double avg_ns = total_ns / kSamples;

    // Should be under 100ns (atomic shared_ptr load + array access)
    EXPECT_LT(avg_ns, 100.0) << "TopicQueueIndex::get() avg latency = " << avg_ns << " ns";
}

}  // namespace
}  // namespace tyche
