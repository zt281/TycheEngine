// Integration tests for SharedMemoryBridge using stub module library.

#include <gtest/gtest.h>

#include <filesystem>

#include "tyche/cpp/engine/shared_memory_bridge.h"

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

}  // namespace
}  // namespace tyche
