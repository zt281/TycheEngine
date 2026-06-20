// Unit tests for tyche::ObjectPool.
//
// Tests:
//   1. Acquire returns object from pool
//   2. Release returns object to pool
//   3. Pool exhaustion returns nullptr
//   4. Available count tracks correctly
//   5. Multi-threaded MPSC stress test
//   6. Destructor drains all objects

#include <gtest/gtest.h>

#include "tyche/cpp/engine/object_pool.h"

#include <atomic>
#include <thread>
#include <vector>

namespace tyche {
namespace {

struct TestItem {
    int value = 0;
    double timestamp = 0.0;

    TestItem() = default;
    explicit TestItem(int v) : value(v), timestamp(0.0) {}
};

TEST(ObjectPoolTest, AcquireReturnsObject) {
    ObjectPool<TestItem, 16> pool;

    TestItem* item = pool.acquire();
    ASSERT_NE(item, nullptr);
    EXPECT_EQ(pool.available(), 15u);

    // Object should be in a usable state (placement-new default constructs)
    item->value = 42;
    item->timestamp = 123.456;
    EXPECT_EQ(item->value, 42);
    EXPECT_DOUBLE_EQ(item->timestamp, 123.456);

    pool.release(item);
    EXPECT_EQ(pool.available(), 16u);
}

TEST(ObjectPoolTest, AcquireExhaustionReturnsNullptr) {
    ObjectPool<TestItem, 4> pool;

    TestItem* items[4];
    for (int i = 0; i < 4; ++i) {
        items[i] = pool.acquire();
        ASSERT_NE(items[i], nullptr);
    }
    EXPECT_EQ(pool.available(), 0u);

    // Pool exhausted
    TestItem* extra = pool.acquire();
    EXPECT_EQ(extra, nullptr);

    // Release one and acquire again
    pool.release(items[2]);
    extra = pool.acquire();
    EXPECT_NE(extra, nullptr);
    EXPECT_EQ(pool.available(), 0u);

    // Cleanup
    for (int i = 0; i < 4; ++i) {
        if (i != 2) pool.release(items[i]);
    }
    pool.release(extra);
    EXPECT_EQ(pool.available(), 4u);
}

TEST(ObjectPoolTest, AvailableCountTracksCorrectly) {
    ObjectPool<TestItem, 100> pool;
    EXPECT_EQ(pool.available(), 100u);
    EXPECT_EQ(pool.total(), 100u);

    std::vector<TestItem*> items;
    for (int i = 0; i < 50; ++i) {
        items.push_back(pool.acquire());
    }
    EXPECT_EQ(pool.available(), 50u);

    for (auto* item : items) {
        pool.release(item);
    }
    EXPECT_EQ(pool.available(), 100u);
}

TEST(ObjectPoolTest, ReuseSameMemory) {
    ObjectPool<TestItem, 8> pool;

    TestItem* item1 = pool.acquire();
    item1->value = 999;
    void* addr1 = item1;

    pool.release(item1);

    TestItem* item2 = pool.acquire();
    void* addr2 = item2;

    // Should reuse the same memory (LIFO stack behavior)
    EXPECT_EQ(addr1, addr2);

    pool.release(item2);
}

TEST(ObjectPoolTest, MultiThreadedStressTest) {
    constexpr size_t kPoolSize = 1024;
    constexpr int kThreads = 8;
    constexpr int kOpsPerThread = 10000;

    ObjectPool<TestItem, kPoolSize> pool;
    std::atomic<int> acquire_failures{0};
    std::atomic<int> total_acquired{0};

    std::vector<std::thread> threads;
    for (int t = 0; t < kThreads; ++t) {
        threads.emplace_back([&]() {
            std::vector<TestItem*> local;
            local.reserve(16);

            for (int i = 0; i < kOpsPerThread; ++i) {
                if (local.size() < 8) {
                    TestItem* item = pool.acquire();
                    if (item) {
                        item->value = i;
                        local.push_back(item);
                        total_acquired.fetch_add(1);
                    } else {
                        acquire_failures.fetch_add(1);
                    }
                } else {
                    // Release half
                    for (size_t j = 0; j < local.size() / 2; ++j) {
                        pool.release(local[j]);
                    }
                    local.erase(local.begin(), local.begin() + local.size() / 2);
                }
            }

            // Release remaining
            for (auto* item : local) {
                pool.release(item);
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    // All objects should be back in the pool
    EXPECT_EQ(pool.available(), kPoolSize);

    // Some acquires may have failed due to contention, but most should succeed
    EXPECT_GT(total_acquired.load(), kThreads * kOpsPerThread / 2);
}

struct CountedItem {
    static int destructor_count;
    int value = 0;
    ~CountedItem() { destructor_count++; }
};

int CountedItem::destructor_count = 0;

TEST(ObjectPoolTest, NonTrivialDestructorCalled) {
    {
        ObjectPool<CountedItem, 4> pool;
        CountedItem* item = pool.acquire();
        item->value = 1;
        pool.release(item);
        // Destructor should have been called in release()
        EXPECT_EQ(CountedItem::destructor_count, 1);
    }
    // Pool destructor does not call destructors for items in free list
    // (they were already called in release())
}

TEST(ObjectPoolTest, LargePoolSize) {
    ObjectPool<TestItem, 65536> pool;
    EXPECT_EQ(pool.available(), 65536u);

    TestItem* item = pool.acquire();
    EXPECT_NE(item, nullptr);
    EXPECT_EQ(pool.available(), 65535u);

    pool.release(item);
    EXPECT_EQ(pool.available(), 65536u);
}

}  // namespace
}  // namespace tyche
