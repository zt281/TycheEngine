// Integration tests for SharedMemoryBridge using stub module library.

#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>
#include <thread>

#include "tyche/cpp/engine/shared_memory_bridge.h"
#include "tyche/cpp/engine/shared_memory_queue.h"

namespace fs = std::filesystem;

namespace tyche {
namespace {

// Helper to get the stub library path
std::string get_stub_lib_path() {
    fs::path test_dir = fs::path(__FILE__).parent_path();
    fs::path stub_dir = test_dir / "stubs" / "stub_shm_lib";

#ifdef _WIN32
    fs::path lib_path = stub_dir / "stub_shm_lib.dll";
#else
    fs::path lib_path = stub_dir / "libstub_shm_lib.so";
#endif
    return lib_path.string();
}

// ── Construction / Lifecycle ────────────────────────────────────────────

TEST(SharedMemoryBridgeTest, Construction) {
    SharedMemoryBridge bridge;
    EXPECT_FALSE(bridge.is_running());
    EXPECT_EQ(bridge.module_count(), 0u);
    EXPECT_EQ(bridge.bridge_count(), 0u);
}

TEST(SharedMemoryBridgeTest, ConfigureEmpty) {
    SharedMemoryBridge bridge;
    bridge.configure({}, {});
    EXPECT_EQ(bridge.module_count(), 0u);
    EXPECT_EQ(bridge.bridge_count(), 0u);
}

// ── Module Loading (requires stub library built) ────────────────────

TEST(SharedMemoryBridgeTest, LoadModuleSuccess) {
    std::string lib_path = get_stub_lib_path();
    if (!fs::exists(lib_path)) {
        GTEST_SKIP() << "Stub library not built: " << lib_path;
    }

    SharedMemoryBridge bridge;
    ShmModuleConfig config;
    config.library_path = lib_path;
    config.shm_queue_name = "test_queue_001";

    std::string module_id = bridge.load_module(config);
    EXPECT_FALSE(module_id.empty());
    EXPECT_EQ(bridge.module_count(), 1u);

    // Cleanup
    bridge.unload_module(config.shm_queue_name);
    EXPECT_EQ(bridge.module_count(), 0u);
}

TEST(SharedMemoryBridgeTest, LoadModuleInvalidPath) {
    SharedMemoryBridge bridge;
    ShmModuleConfig config;
    config.library_path = "/nonexistent/path/lib.so";
    config.shm_queue_name = "test_queue_invalid";

    std::string module_id = bridge.load_module(config);
    EXPECT_TRUE(module_id.empty());
    EXPECT_EQ(bridge.module_count(), 0u);
}

TEST(SharedMemoryBridgeTest, UnloadNonexistentModule) {
    SharedMemoryBridge bridge;
    // Should not crash
    bridge.unload_module("nonexistent_queue");
    EXPECT_EQ(bridge.module_count(), 0u);
}

// ── Raw Bridge Config ───────────────────────────────────────────────

TEST(SharedMemoryBridgeTest, RawBridgeConfig) {
    SharedMemoryBridge bridge;

    ShmBridgeConfig raw_config;
    raw_config.shm_queue_name = "raw_bridge_queue";
    raw_config.zmq_topic = "raw_topic";

    bridge.configure({}, {raw_config});
    EXPECT_EQ(bridge.bridge_count(), 1u);
}

// ── Snapshot / AdaptiveSpin / Zero-allocation tests ─────────────────

TEST(SharedMemoryBridgeTest, RebuildSnapshotOnConfigure) {
    // After configure, bridge_count should reflect bridges
    SharedMemoryBridge bridge;

    ShmBridgeConfig raw1;
    raw1.shm_queue_name = "snap_bridge_1";
    raw1.zmq_topic = "topic_1";

    ShmBridgeConfig raw2;
    raw2.shm_queue_name = "snap_bridge_2";
    raw2.zmq_topic = "topic_2";

    bridge.configure({}, {raw1, raw2});
    EXPECT_EQ(bridge.bridge_count(), 2u);
}

TEST(SharedMemoryBridgeTest, StartStopCycle) {
    // Verify start/stop doesn't crash and state transitions correctly
    SharedMemoryBridge bridge;
    EXPECT_FALSE(bridge.is_running());

    bridge.start(nullptr);  // null engine is fine for lifecycle test
    EXPECT_TRUE(bridge.is_running());

    bridge.stop();
    EXPECT_FALSE(bridge.is_running());
}

TEST(SharedMemoryBridgeTest, DoubleStartIgnored) {
    SharedMemoryBridge bridge;
    bridge.start(nullptr);
    bridge.start(nullptr);  // should be ignored (already running)
    EXPECT_TRUE(bridge.is_running());
    bridge.stop();
}

TEST(SharedMemoryBridgeTest, DoubleStopSafe) {
    SharedMemoryBridge bridge;
    bridge.start(nullptr);
    bridge.stop();
    bridge.stop();  // second stop should not crash
    EXPECT_FALSE(bridge.is_running());
}

TEST(SharedMemoryBridgeTest, ModuleVersionCheckAcceptsCompatible) {
    std::string lib_path = get_stub_lib_path();
    if (!fs::exists(lib_path)) {
        GTEST_SKIP() << "Stub library not built: " << lib_path;
    }

    SharedMemoryBridge bridge;
    ShmModuleConfig config;
    config.library_path = lib_path;
    config.shm_queue_name = "test_version_compat";

    std::string id = bridge.load_module(config);
    // If stub exports tyche_module_version() with matching ABI, should succeed.
    // If stub doesn't export it, should still succeed with warning.
    EXPECT_FALSE(id.empty());
    bridge.unload_module("test_version_compat");
}

TEST(SharedMemoryBridgeTest, UnloadModuleWithTimeout) {
    // Verify unload_module doesn't hang indefinitely
    std::string lib_path = get_stub_lib_path();
    if (!fs::exists(lib_path)) {
        GTEST_SKIP() << "Stub library not built: " << lib_path;
    }

    SharedMemoryBridge bridge;
    ShmModuleConfig config;
    config.library_path = lib_path;
    config.shm_queue_name = "test_timeout_unload";

    std::string id = bridge.load_module(config);
    if (id.empty()) {
        GTEST_SKIP() << "Module failed to load";
    }

    // Unload should complete within a reasonable time
    auto start = std::chrono::steady_clock::now();
    bridge.unload_module("test_timeout_unload");
    auto elapsed = std::chrono::steady_clock::now() - start;

    // Should finish within MODULE_STOP_TIMEOUT_SEC + margin (8s max)
    EXPECT_LT(std::chrono::duration_cast<std::chrono::seconds>(elapsed).count(), 8);
    EXPECT_EQ(bridge.module_count(), 0u);
}

TEST(SharedMemoryBridgeTest, WorkerLoopUsesAdaptiveSpin) {
    // Start bridge, wait briefly, verify it's responsive (doesn't hang on 1ms sleep)
    SharedMemoryBridge bridge;
    bridge.start(nullptr);

    // Worker should be alive and responsive
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    EXPECT_TRUE(bridge.is_running());

    bridge.stop();
    EXPECT_FALSE(bridge.is_running());
}

}  // namespace
}  // namespace tyche
