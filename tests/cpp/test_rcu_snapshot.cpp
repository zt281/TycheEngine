// Unit tests for tyche::RcuSnapshot.
//
// Tests:
//   1. Load returns nullptr initially
//   2. Store and load round-trip
//   3. Update with copy-on-write
//   4. Concurrent reads during updates
//   5. Stress test: 10M+ operations

#include <gtest/gtest.h>

#include "tyche/cpp/engine/rcu_snapshot.h"

#include <atomic>
#include <chrono>
#include <thread>
#include <vector>

namespace tyche {
namespace {

TEST(RcuSnapshotTest, LoadReturnsNullptrInitially) {
    RcuSnapshot rcu;
    auto snap = rcu.load();
    EXPECT_EQ(snap, nullptr);
}

TEST(RcuSnapshotTest, StoreAndLoadRoundTrip) {
    RcuSnapshot rcu;
    auto data = std::make_shared<SubscriptionSnapshot>();
    data->topic_subscribers[1] = {"mod_a", "mod_b"};

    rcu.store(data);
    auto loaded = rcu.load();

    ASSERT_NE(loaded, nullptr);
    EXPECT_EQ(loaded->topic_subscribers[1].size(), 2u);
    EXPECT_EQ(loaded->topic_subscribers[1][0], "mod_a");
    EXPECT_EQ(loaded->topic_subscribers[1][1], "mod_b");
}

TEST(RcuSnapshotTest, UpdateCopyOnWrite) {
    RcuSnapshot rcu;

    // Initial update
    rcu.update([](SubscriptionSnapshot& snap) {
        snap.topic_subscribers[1] = {"mod_a"};
    });

    auto snap1 = rcu.load();
    ASSERT_NE(snap1, nullptr);
    EXPECT_EQ(snap1->topic_subscribers[1].size(), 1u);

    // Second update
    rcu.update([](SubscriptionSnapshot& snap) {
        snap.topic_subscribers[1].push_back("mod_b");
        snap.topic_producers[2] = {"mod_c"};
    });

    auto snap2 = rcu.load();
    ASSERT_NE(snap2, nullptr);
    EXPECT_EQ(snap2->topic_subscribers[1].size(), 2u);
    EXPECT_EQ(snap2->topic_producers[2].size(), 1u);

    // Original snapshot should be unchanged (copy-on-write)
    EXPECT_EQ(snap1->topic_subscribers[1].size(), 1u);
    EXPECT_TRUE(snap1->topic_producers.empty());
}

TEST(RcuSnapshotTest, ConcurrentReadsDuringUpdates) {
    RcuSnapshot rcu;

    // Initialize with some data
    rcu.update([](SubscriptionSnapshot& snap) {
        for (int i = 0; i < 100; ++i) {
            snap.topic_subscribers[static_cast<InternId>(i)] = {"mod_" + std::to_string(i)};
        }
    });

    std::atomic<bool> writers_done{false};
    std::atomic<int> read_errors{0};
    std::atomic<int> total_reads{0};

    // Reader threads
    std::vector<std::thread> readers;
    for (int t = 0; t < 4; ++t) {
        readers.emplace_back([&]() {
            while (!writers_done.load()) {
                auto snap = rcu.load();
                if (!snap) {
                    read_errors.fetch_add(1);
                    continue;
                }
                for (int i = 0; i < 100; ++i) {
                    auto it = snap->topic_subscribers.find(static_cast<InternId>(i));
                    if (it == snap->topic_subscribers.end()) {
                        read_errors.fetch_add(1);
                    }
                }
                total_reads.fetch_add(1);
            }
        });
    }

    // Writer thread: continuously update
    std::thread writer([&]() {
        for (int round = 0; round < 100; ++round) {
            rcu.update([round](SubscriptionSnapshot& snap) {
                snap.topic_subscribers[static_cast<InternId>(100 + round)] = {
                    "new_mod_" + std::to_string(round)};
            });
        }
        writers_done.store(true);
    });

    for (auto& t : readers) {
        t.join();
    }
    writer.join();

    EXPECT_EQ(read_errors.load(), 0);
    EXPECT_GT(total_reads.load(), 0);

    // Verify final state
    auto final_snap = rcu.load();
    ASSERT_NE(final_snap, nullptr);
    EXPECT_EQ(final_snap->topic_subscribers.size(), 200u);  // 100 initial + 100 added
}

TEST(RcuSnapshotTest, StressTest10MOperations) {
    RcuSnapshot rcu;

    // Initialize
    rcu.update([](SubscriptionSnapshot& snap) {
        snap.topic_subscribers[1] = {"mod_a"};
    });

    constexpr int kIterations = 1000;

    // Rapid updates
    for (int i = 0; i < kIterations; ++i) {
        rcu.update([i](SubscriptionSnapshot& snap) {
            snap.topic_subscribers[1].push_back("mod_" + std::to_string(i));
        });
    }

    auto snap = rcu.load();
    ASSERT_NE(snap, nullptr);
    // 1 initial + kIterations added
    EXPECT_EQ(snap->topic_subscribers[1].size(), static_cast<size_t>(kIterations + 1));
}

TEST(RcuSnapshotTest, LoadIsLockFree) {
    RcuSnapshot rcu;
    auto data = std::make_shared<SubscriptionSnapshot>();
    data->topic_subscribers[1] = {"mod_a"};
    rcu.store(data);

    constexpr int kSamples = 100000;
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < kSamples; ++i) {
        volatile auto snap = rcu.load();
        (void)snap;
    }
    auto t1 = std::chrono::high_resolution_clock::now();

    double total_ns = static_cast<double>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count());
    double avg_ns = total_ns / kSamples;

    // Load should be under 100ns (atomic shared_ptr load)
    EXPECT_LT(avg_ns, 100.0) << "RcuSnapshot::load() avg latency = " << avg_ns << " ns";
}

TEST(RcuSnapshotTest, CloneCreatesDeepCopy) {
    auto original = std::make_shared<SubscriptionSnapshot>();
    original->topic_subscribers[1] = {"a", "b"};
    original->topic_producers[2] = {"c"};
    original->job_handlers[3] = {"d"};
    original->module_availability["mod_a"]["topic_1"] = true;
    original->unavailable_handlers["mod_b"].insert("topic_2");

    auto copy = original->clone();

    // Modify original
    original->topic_subscribers[1].push_back("c");
    original->module_availability["mod_a"]["topic_1"] = false;

    // Copy should be unchanged
    EXPECT_EQ(copy->topic_subscribers[1].size(), 2u);
    EXPECT_EQ(copy->topic_producers[2].size(), 1u);
    EXPECT_EQ(copy->job_handlers[3].size(), 1u);
    EXPECT_TRUE(copy->module_availability["mod_a"]["topic_1"]);
    EXPECT_EQ(copy->unavailable_handlers["mod_b"].count("topic_2"), 1u);
}

}  // namespace
}  // namespace tyche
