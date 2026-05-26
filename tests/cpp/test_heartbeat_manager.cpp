// Unit tests for tyche::HeartbeatManager - Paranoid Pirate Pattern heartbeat.

#include <gtest/gtest.h>

#include <string>
#include <thread>
#include <vector>

#include "tyche/cpp/engine/heartbeat_manager.h"

namespace tyche {
namespace {

// ── Construction ──────────────────────────────────────────────────────

TEST(HeartbeatManagerTest, DefaultConstruction) {
    HeartbeatManager mgr;
    EXPECT_EQ(mgr.size(), 0u);
}

TEST(HeartbeatManagerTest, CustomIntervalAndLiveness) {
    HeartbeatManager mgr(2.0, 5);
    EXPECT_EQ(mgr.size(), 0u);
}

// ── Registration ──────────────────────────────────────────────────────

TEST(HeartbeatManagerTest, RegisterModule) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_abc123");

    EXPECT_TRUE(mgr.is_registered("mod_abc123"));
    EXPECT_EQ(mgr.size(), 1u);
    // Grace period: liveness = 3 * 2 = 6
    EXPECT_EQ(mgr.get_liveness("mod_abc123"), 6);
}

TEST(HeartbeatManagerTest, RegisterMultipleModules) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");
    mgr.register_module("mod_b");
    mgr.register_module("mod_c");

    EXPECT_EQ(mgr.size(), 3u);
    EXPECT_TRUE(mgr.is_registered("mod_a"));
    EXPECT_TRUE(mgr.is_registered("mod_b"));
    EXPECT_TRUE(mgr.is_registered("mod_c"));
}

TEST(HeartbeatManagerTest, UnregisteredModuleNotFound) {
    HeartbeatManager mgr;
    EXPECT_FALSE(mgr.is_registered("nonexistent"));
    EXPECT_EQ(mgr.get_liveness("nonexistent"), -1);
}

// ── Update (Heartbeat Received) ───────────────────────────────────────

TEST(HeartbeatManagerTest, UpdateResetsLiveness) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");

    // Tick a few times to reduce liveness
    mgr.tick_all();  // liveness: 6 -> 5
    mgr.tick_all();  // liveness: 5 -> 4

    // Update should reset to default liveness (3)
    mgr.update("mod_a");
    EXPECT_EQ(mgr.get_liveness("mod_a"), 3);
}

TEST(HeartbeatManagerTest, UpdateNonexistentModuleDoesNothing) {
    HeartbeatManager mgr(1.0, 3);
    // Should not throw or crash
    mgr.update("nonexistent");
    EXPECT_EQ(mgr.size(), 0u);
}

// ── Tick and Expiry ───────────────────────────────────────────────────

TEST(HeartbeatManagerTest, TickDecrementsLiveness) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");

    // Grace period liveness = 6
    auto expired = mgr.tick_all();
    EXPECT_TRUE(expired.empty());
    EXPECT_EQ(mgr.get_liveness("mod_a"), 5);  // 6 -> 5

    expired = mgr.tick_all();
    EXPECT_TRUE(expired.empty());
    EXPECT_EQ(mgr.get_liveness("mod_a"), 4);  // 5 -> 4
}

TEST(HeartbeatManagerTest, ModuleExpiresAfterEnoughTicks) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");

    // Grace period liveness = 6, need 6 ticks to expire
    for (int i = 0; i < 5; ++i) {
        auto expired = mgr.tick_all();
        EXPECT_TRUE(expired.empty());
    }
    // 6th tick: liveness = 1 -> 0, expired
    auto expired = mgr.tick_all();
    EXPECT_EQ(expired.size(), 1u);
    EXPECT_EQ(expired[0], "mod_a");

    // Module should be removed
    EXPECT_FALSE(mgr.is_registered("mod_a"));
    EXPECT_EQ(mgr.size(), 0u);
}

TEST(HeartbeatManagerTest, HeartbeatKeepsModuleAlive) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");

    // Tick many times, but update in between
    for (int round = 0; round < 10; ++round) {
        mgr.tick_all();
        mgr.tick_all();
        mgr.update("mod_a");  // reset to 3
    }

    // Should still be alive
    EXPECT_TRUE(mgr.is_registered("mod_a"));
    EXPECT_EQ(mgr.get_liveness("mod_a"), 3);
}

// ── Unregister ────────────────────────────────────────────────────────

TEST(HeartbeatManagerTest, UnregisterModule) {
    HeartbeatManager mgr(1.0, 3);
    mgr.register_module("mod_a");
    mgr.register_module("mod_b");

    mgr.unregister("mod_a");
    EXPECT_FALSE(mgr.is_registered("mod_a"));
    EXPECT_TRUE(mgr.is_registered("mod_b"));
    EXPECT_EQ(mgr.size(), 1u);
}

TEST(HeartbeatManagerTest, UnregisterNonexistentDoesNothing) {
    HeartbeatManager mgr;
    mgr.unregister("nonexistent");
    EXPECT_EQ(mgr.size(), 0u);
}

// ── Multiple Expirations ──────────────────────────────────────────────

TEST(HeartbeatManagerTest, MultipleModulesExpireSimultaneously) {
    HeartbeatManager mgr(1.0, 1);  // liveness=1, grace=2
    mgr.register_module("mod_a");
    mgr.register_module("mod_b");

    // Both have liveness=2 (grace period)
    mgr.tick_all();  // both -> 1
    auto expired = mgr.tick_all();  // both -> 0

    EXPECT_EQ(expired.size(), 2u);
    EXPECT_EQ(mgr.size(), 0u);
}

// ── Thread Safety ─────────────────────────────────────────────────────

TEST(HeartbeatManagerTest, ConcurrentAccess) {
    HeartbeatManager mgr(1.0, 5);

    // Register a bunch of modules
    for (int i = 0; i < 10; ++i) {
        mgr.register_module("mod_" + std::to_string(i));
    }

    // Concurrent readers and writers
    std::vector<std::thread> threads;

    // Updater thread
    threads.emplace_back([&mgr] {
        for (int i = 0; i < 100; ++i) {
            mgr.update("mod_" + std::to_string(i % 10));
            std::this_thread::yield();
        }
    });

    // Ticker thread
    threads.emplace_back([&mgr] {
        for (int i = 0; i < 5; ++i) {
            mgr.tick_all();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    });

    // Reader thread
    threads.emplace_back([&mgr] {
        for (int i = 0; i < 100; ++i) {
            mgr.is_registered("mod_" + std::to_string(i % 10));
            mgr.get_liveness("mod_" + std::to_string(i % 10));
            mgr.size();
            std::this_thread::yield();
        }
    });

    for (auto& t : threads) {
        t.join();
    }

    // Should not crash - basic sanity check
    EXPECT_LE(mgr.size(), 10u);
}

}  // namespace
}  // namespace tyche
