// Unit tests for tyche::ShardedTopicQueueMap - lock-free topic queue lookup.

#include <gtest/gtest.h>

#include <string>
#include <thread>
#include <vector>

#include "tyche/cpp/engine/sharded_topic_map.h"
#include "tyche/cpp/engine/topic_queue.h"

namespace tyche {
namespace {

// ── Construction ──────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, DefaultConstruction) {
    ShardedTopicQueueMap map;
    EXPECT_EQ(map.size(), 0u);
}

TEST(ShardedTopicQueueMapTest, CustomBucketCount) {
    ShardedTopicQueueMap map(64);
    EXPECT_EQ(map.size(), 0u);
}

TEST(ShardedTopicQueueMapTest, NonPowerOfTwoBucketCountRounded) {
    // 100 is not a power of two; should round up to 128
    ShardedTopicQueueMap map(100);
    EXPECT_EQ(map.size(), 0u);
    // Verify it works correctly by creating many topics
    for (int i = 0; i < 200; ++i) {
        map.get_or_create("topic_" + std::to_string(i), 100);
    }
    EXPECT_EQ(map.size(), 200u);
}

// ── Get or create ─────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, GetOrCreateReturnsQueue) {
    ShardedTopicQueueMap map;
    auto q = map.get_or_create("tick", 100);
    EXPECT_NE(q, nullptr);
    EXPECT_EQ(map.size(), 1u);
}

TEST(ShardedTopicQueueMapTest, GetOrCreateSameTopicReturnsSameQueue) {
    ShardedTopicQueueMap map;
    auto q1 = map.get_or_create("tick", 100);
    auto q2 = map.get_or_create("tick", 100);
    EXPECT_EQ(q1, q2);
    EXPECT_EQ(map.size(), 1u);
}

TEST(ShardedTopicQueueMapTest, GetOrCreateWithOutLastAccess) {
    ShardedTopicQueueMap map;
    double last_access = -1.0;
    auto q1 = map.get_or_create("tick", 100, &last_access);
    EXPECT_NE(q1, nullptr);
    EXPECT_DOUBLE_EQ(last_access, 0.0);  // newly created, last_access = 0.0

    map.touch("tick", 1234.5);
    last_access = -1.0;
    auto q2 = map.get_or_create("tick", 100, &last_access);
    EXPECT_EQ(q1, q2);
    EXPECT_DOUBLE_EQ(last_access, 1234.5);  // existing, returns last_access
}

TEST(ShardedTopicQueueMapTest, GetOrCreateDifferentTopicsReturnsDifferentQueues) {
    ShardedTopicQueueMap map;
    auto q1 = map.get_or_create("tick", 100);
    auto q2 = map.get_or_create("quote", 100);
    EXPECT_NE(q1, q2);
    EXPECT_EQ(map.size(), 2u);
}

// ── Find ──────────────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, FindExistingReturnsQueue) {
    ShardedTopicQueueMap map;
    auto created = map.get_or_create("tick", 100);
    auto found = map.find("tick");
    EXPECT_NE(found, nullptr);
    EXPECT_EQ(created, found);
}

TEST(ShardedTopicQueueMapTest, FindNonexistentReturnsNull) {
    ShardedTopicQueueMap map;
    EXPECT_EQ(map.find("missing"), nullptr);
}

// ── Get raw pointer ───────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, GetRawReturnsSameAsFind) {
    ShardedTopicQueueMap map;
    auto created = map.get_or_create("tick", 100);
    auto* raw = map.get_raw("tick");
    EXPECT_EQ(raw, created.get());
}

TEST(ShardedTopicQueueMapTest, GetRawNonexistentReturnsNull) {
    ShardedTopicQueueMap map;
    EXPECT_EQ(map.get_raw("missing"), nullptr);
}

// ── Erase ─────────────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, EraseRemovesQueue) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);
    EXPECT_EQ(map.size(), 1u);

    map.erase("tick");
    EXPECT_EQ(map.size(), 0u);
    EXPECT_EQ(map.find("tick"), nullptr);
}

TEST(ShardedTopicQueueMapTest, EraseNonexistentDoesNothing) {
    ShardedTopicQueueMap map;
    map.erase("missing");  // should not crash
    EXPECT_EQ(map.size(), 0u);
}

TEST(ShardedTopicQueueMapTest, EraseOneOfMany) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);
    map.get_or_create("quote", 100);
    map.get_or_create("trade", 100);

    map.erase("quote");
    EXPECT_EQ(map.size(), 2u);
    EXPECT_EQ(map.find("quote"), nullptr);
    EXPECT_NE(map.find("tick"), nullptr);
    EXPECT_NE(map.find("trade"), nullptr);
}

// ── Snapshot ──────────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, SnapshotEmpty) {
    ShardedTopicQueueMap map;
    auto snap = map.snapshot();
    EXPECT_TRUE(snap.empty());
}

TEST(ShardedTopicQueueMapTest, SnapshotContainsAllTopics) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);
    map.get_or_create("quote", 100);

    auto snap = map.snapshot();
    EXPECT_EQ(snap.size(), 2u);
}

TEST(ShardedTopicQueueMapTest, SnapshotWithManyBuckets) {
    ShardedTopicQueueMap map(4);  // small bucket count to force collisions
    for (int i = 0; i < 20; ++i) {
        map.get_or_create("topic_" + std::to_string(i), 100);
    }
    auto snap = map.snapshot();
    EXPECT_EQ(snap.size(), 20u);
}

// ── Touch / last_access ───────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, TouchUpdatesLastAccess) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);

    double before = map.last_access("tick");
    EXPECT_DOUBLE_EQ(before, 0.0);

    map.touch("tick", 1234.5);
    double after = map.last_access("tick");
    EXPECT_DOUBLE_EQ(after, 1234.5);
}

TEST(ShardedTopicQueueMapTest, LastAccessNonexistentReturnsZero) {
    ShardedTopicQueueMap map;
    EXPECT_DOUBLE_EQ(map.last_access("missing"), 0.0);
}

TEST(ShardedTopicQueueMapTest, TouchWithoutCreate) {
    ShardedTopicQueueMap map;
    map.touch("tick", 100.0);
    EXPECT_DOUBLE_EQ(map.last_access("tick"), 100.0);
}

TEST(ShardedTopicQueueMapTest, TouchExistingUpdatesValue) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);
    map.touch("tick", 50.0);
    EXPECT_DOUBLE_EQ(map.last_access("tick"), 50.0);
    map.touch("tick", 100.0);
    EXPECT_DOUBLE_EQ(map.last_access("tick"), 100.0);
}

// ── Queue functionality via map ───────────────────────────────────────

TEST(ShardedTopicQueueMapTest, QueuePutGet) {
    ShardedTopicQueueMap map;
    auto q = map.get_or_create("tick", 10);

    std::vector<Frame> frames;
    frames.emplace_back(reinterpret_cast<const uint8_t*>("data"), 4);
    QueueItem item(1.0, std::move(frames));

    EXPECT_TRUE(q->put(std::move(item)));

    auto got = q->get();
    ASSERT_TRUE(got.has_value());
    EXPECT_EQ(got->frames.size(), 1u);
}

// ── Concurrent access ───────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, ConcurrentGetOrCreateDifferentTopics) {
    ShardedTopicQueueMap map;
    constexpr int NUM_THREADS = 10;
    constexpr int TOPICS_PER_THREAD = 10;

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&map, t, TOPICS_PER_THREAD] {
            for (int i = 0; i < TOPICS_PER_THREAD; ++i) {
                map.get_or_create("topic_" + std::to_string(t) + "_" + std::to_string(i), 100);
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(map.size(), static_cast<size_t>(NUM_THREADS * TOPICS_PER_THREAD));
}

TEST(ShardedTopicQueueMapTest, ConcurrentGetOrCreateSameTopic) {
    ShardedTopicQueueMap map;
    constexpr int NUM_THREADS = 20;

    std::vector<std::shared_ptr<TopicQueue>> queues(NUM_THREADS);
    std::vector<std::thread> threads;

    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&map, &queues, t] {
            queues[t] = map.get_or_create("shared_topic", 100);
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    // All threads should get the same queue
    for (int i = 1; i < NUM_THREADS; ++i) {
        EXPECT_EQ(queues[0], queues[i]);
    }
    EXPECT_EQ(map.size(), 1u);
}

TEST(ShardedTopicQueueMapTest, ConcurrentMixedOperations) {
    ShardedTopicQueueMap map;
    constexpr int NUM_THREADS = 10;

    // Pre-create some topics
    for (int i = 0; i < 20; ++i) {
        map.get_or_create("pre_" + std::to_string(i), 100);
    }

    std::vector<std::thread> threads;

    // Creators
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&map, t] {
            for (int i = 0; i < 50; ++i) {
                map.get_or_create("new_" + std::to_string(t) + "_" + std::to_string(i), 100);
            }
        });
    }

    // Readers + touchers
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&map, t] {
            for (int i = 0; i < 100; ++i) {
                map.find("pre_" + std::to_string(i % 20));
                map.touch("pre_" + std::to_string(i % 20), static_cast<double>(i));
                map.last_access("pre_" + std::to_string(i % 20));
                map.snapshot();
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_GE(map.size(), 20u);
}

TEST(ShardedTopicQueueMapTest, ConcurrentEraseAndCreate) {
    ShardedTopicQueueMap map;
    constexpr int NUM_THREADS = 8;
    constexpr int OPS_PER_THREAD = 50;

    // Pre-create topics
    for (int i = 0; i < 20; ++i) {
        map.get_or_create("topic_" + std::to_string(i), 100);
    }

    std::vector<std::thread> threads;

    // Erasers
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&map, t, OPS_PER_THREAD] {
            for (int i = 0; i < OPS_PER_THREAD; ++i) {
                map.erase("topic_" + std::to_string(i % 20));
            }
        });
    }

    // Re-creators (more ops than erasers to ensure some topics survive)
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&map, t, OPS_PER_THREAD] {
            for (int i = 0; i < OPS_PER_THREAD * 2; ++i) {
                map.get_or_create("topic_" + std::to_string(i % 20), 100);
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    // With more create ops than erase ops, some topics should survive
    EXPECT_GT(map.size(), 0u);
    EXPECT_LE(map.size(), 20u);
}

TEST(ShardedTopicQueueMapTest, HashCollisionSameBucket) {
    // Use a very small bucket count to force collisions
    ShardedTopicQueueMap map(2);

    map.get_or_create("tick", 100);
    map.get_or_create("quote", 100);
    map.get_or_create("trade", 100);
    map.get_or_create("order", 100);

    EXPECT_EQ(map.size(), 4u);

    // All should be findable
    EXPECT_NE(map.find("tick"), nullptr);
    EXPECT_NE(map.find("quote"), nullptr);
    EXPECT_NE(map.find("trade"), nullptr);
    EXPECT_NE(map.find("order"), nullptr);

    // Erase one from a potentially colliding bucket
    map.erase("quote");
    EXPECT_EQ(map.find("quote"), nullptr);
    EXPECT_NE(map.find("tick"), nullptr);
    EXPECT_EQ(map.size(), 3u);
}

TEST(ShardedTopicQueueMapTest, EraseUpdatesLastAccess) {
    ShardedTopicQueueMap map;
    map.get_or_create("tick", 100);
    map.touch("tick", 50.0);
    EXPECT_DOUBLE_EQ(map.last_access("tick"), 50.0);

    map.erase("tick");
    EXPECT_DOUBLE_EQ(map.last_access("tick"), 0.0);
    EXPECT_EQ(map.find("tick"), nullptr);
}

// ── Size consistency ────────────────────────────────────────────────────

TEST(ShardedTopicQueueMapTest, SizeAfterManyOperations) {
    ShardedTopicQueueMap map;

    for (int i = 0; i < 100; ++i) {
        map.get_or_create("topic_" + std::to_string(i), 100);
    }
    EXPECT_EQ(map.size(), 100u);

    for (int i = 0; i < 50; ++i) {
        map.erase("topic_" + std::to_string(i));
    }
    EXPECT_EQ(map.size(), 50u);

    // Re-create some erased topics
    for (int i = 0; i < 25; ++i) {
        map.get_or_create("topic_" + std::to_string(i), 100);
    }
    EXPECT_EQ(map.size(), 75u);
}

}  // namespace
}  // namespace tyche
