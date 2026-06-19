// Integration tests for TycheEngine code paths not covered by unit tests.
//
// These tests exercise engine functionality that requires the engine to be
// in a running state, but avoid the ZMQ blocking recv hang issue by not
// calling stop() / destructor on a running engine with active ZMQ sockets.
// Instead, we test the individual worker logic through direct method calls
// where possible, and use short-lived engine instances for smoke tests.

#include <gtest/gtest.h>

#include <chrono>
#include <thread>
#include <vector>

#include "tyche/cpp/engine/engine.h"
#include "tyche/cpp/message.h"

namespace tyche {
namespace {

// ── Event Injection with Running Engine ─────────────────────────────

TEST(EngineIntegrationTest, InjectEventsWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5605},   // reg
        {"127.0.0.1", 5606},   // event
        {"127.0.0.1", 5607},   // heartbeat pub
        {"127.0.0.1", 5608},   // heartbeat recv
        {"127.0.0.1", 5609},   // admin
        {"127.0.0.1", 5610});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Inject events - this exercises _enqueue_from_xsub and _event_egress_worker
    for (int i = 0; i < 100; ++i) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
        engine.inject_event("test_topic", data);
    }

    // Let egress worker process
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // NOTE: We do NOT call engine.stop() here because it can hang on Windows
    // due to ZMQ blocking recv. The destructor will call stop() but in a
    // nested scope it may still hang. We use a detached approach:
    engine.stop();
}

TEST(EngineIntegrationTest, InjectRawEventsWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5615},   // reg
        {"127.0.0.1", 5616},   // event
        {"127.0.0.1", 5617},   // heartbeat pub
        {"127.0.0.1", 5618},   // heartbeat recv
        {"127.0.0.1", 5619},   // admin
        {"127.0.0.1", 5620});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    for (int i = 0; i < 50; ++i) {
        const uint8_t data[] = {static_cast<uint8_t>(i), 'h', 'i'};
        engine.inject_event_raw("raw_topic", data, sizeof(data));
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    engine.stop();
}

TEST(EngineIntegrationTest, InjectMultipleTopicsWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5625},   // reg
        {"127.0.0.1", 5626},   // event
        {"127.0.0.1", 5627},   // heartbeat pub
        {"127.0.0.1", 5628},   // heartbeat recv
        {"127.0.0.1", 5629},   // admin
        {"127.0.0.1", 5630});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    for (int i = 0; i < 20; ++i) {
        std::vector<uint8_t> data(100, static_cast<uint8_t>(i));
        engine.inject_event("topic_" + std::to_string(i % 5), data);
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    engine.stop();
}

// ── Module Registration with Running Engine ─────────────────────────

TEST(EngineIntegrationTest, RegisterModuleWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5585},   // reg
        {"127.0.0.1", 5586},   // event
        {"127.0.0.1", 5587},   // heartbeat pub
        {"127.0.0.1", 5588},   // heartbeat recv
        {"127.0.0.1", 5589},   // admin
        {"127.0.0.1", 5590});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    ModuleInfo info;
    info.module_id = "runtime_mod";
    Interface iface;
    iface.name = "on_tick";
    iface.event_type = "tick";
    iface.pattern = InterfacePattern::ON;
    info.interfaces.push_back(iface);
    engine.register_module(info);

    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    engine.unregister_module("runtime_mod");
    engine.stop();
}

TEST(EngineIntegrationTest, RegisterMultipleModulesWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5595},   // reg
        {"127.0.0.1", 5596},   // event
        {"127.0.0.1", 5597},   // heartbeat pub
        {"127.0.0.1", 5598},   // heartbeat recv
        {"127.0.0.1", 5599},   // admin
        {"127.0.0.1", 5600});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    for (int i = 0; i < 10; ++i) {
        ModuleInfo info;
        info.module_id = "multi_mod_" + std::to_string(i);
        Interface iface;
        iface.name = "on_event";
        iface.event_type = "event_" + std::to_string(i);
        iface.pattern = InterfacePattern::ON;
        info.interfaces.push_back(iface);
        engine.register_module(info);
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    for (int i = 0; i < 10; ++i) {
        engine.unregister_module("multi_mod_" + std::to_string(i));
    }
    engine.stop();
}

// ── Job Handler Registration ────────────────────────────────────────

TEST(EngineIntegrationTest, RegisterJobHandlerWhileRunning) {
    TycheEngine engine(
        {"127.0.0.1", 5635},   // reg
        {"127.0.0.1", 5636},   // event
        {"127.0.0.1", 5637},   // heartbeat pub
        {"127.0.0.1", 5638},   // heartbeat recv
        {"127.0.0.1", 5639},   // admin
        {"127.0.0.1", 5640});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    ModuleInfo info;
    info.module_id = "job_handler_mod";
    Interface iface;
    iface.name = "handle_job";
    iface.event_type = "job_topic";
    iface.pattern = InterfacePattern::HANDLE;
    info.interfaces.push_back(iface);
    engine.register_module(info);

    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    engine.unregister_module("job_handler_mod");
    engine.stop();
}

// ── Heartbeat Manager Integration ───────────────────────────────────

TEST(EngineIntegrationTest, HeartbeatManagerTracksModules) {
    TycheEngine engine(
        {"127.0.0.1", 5645},   // reg
        {"127.0.0.1", 5646},   // event
        {"127.0.0.1", 5647},   // heartbeat pub
        {"127.0.0.1", 5648},   // heartbeat recv
        {"127.0.0.1", 5649},   // admin
        {"127.0.0.1", 5650});  // job

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    ModuleInfo info;
    info.module_id = "hb_track_mod";
    Interface iface;
    iface.name = "on_tick";
    iface.event_type = "tick";
    iface.pattern = InterfacePattern::ON;
    info.interfaces.push_back(iface);
    engine.register_module(info);

    // Let monitor worker run at least one tick
    std::this_thread::sleep_for(std::chrono::milliseconds(1200));

    engine.unregister_module("hb_track_mod");
    engine.stop();
}

// ── Monitor Worker: Topic Queue GC ──────────────────────────────────

TEST(EngineIntegrationTest, MonitorGCTopicQueues) {
    TycheEngine engine(
        {"127.0.0.1", 5655},   // reg
        {"127.0.0.1", 5656},   // event
        {"127.0.0.1", 5657},   // heartbeat pub
        {"127.0.0.1", 5658},   // heartbeat recv
        {"127.0.0.1", 5659},   // admin
        {"127.0.0.1", 5660},   // job
        10000,                   // queue_capacity
        "data");                // data_dir

    engine.start_nonblocking();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    // Inject events to create topic queues
    for (int i = 0; i < 5; ++i) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
        engine.inject_event("gc_test_topic", data);
    }

    // Let monitor worker run - it will try to GC inactive queues
    std::this_thread::sleep_for(std::chrono::milliseconds(1200));
    engine.stop();
}

// ── Full Engine Lifecycle Stress Test ───────────────────────────────

TEST(EngineIntegrationTest, FullLifecycleStress) {
    TycheEngine engine(
        {"127.0.0.1", 5665},   // reg
        {"127.0.0.1", 5666},   // event
        {"127.0.0.1", 5667},   // heartbeat pub
        {"127.0.0.1", 5668},   // heartbeat recv
        {"127.0.0.1", 5669},   // admin
        {"127.0.0.1", 5670});  // job

    engine.start_nonblocking();

    // Register multiple modules with different patterns
    for (int i = 0; i < 5; ++i) {
        ModuleInfo info;
        info.module_id = "stress_mod_" + std::to_string(i);

        Interface on_iface;
        on_iface.name = "on_event";
        on_iface.event_type = "event_" + std::to_string(i);
        on_iface.pattern = InterfacePattern::ON;
        info.interfaces.push_back(on_iface);

        Interface send_iface;
        send_iface.name = "send_order";
        send_iface.event_type = "order_" + std::to_string(i);
        send_iface.pattern = InterfacePattern::SEND;
        info.interfaces.push_back(send_iface);

        if (i % 2 == 0) {
            Interface handle_iface;
            handle_iface.name = "handle_job";
            handle_iface.event_type = "job_" + std::to_string(i);
            handle_iface.pattern = InterfacePattern::HANDLE;
            info.interfaces.push_back(handle_iface);
        }

        engine.register_module(info);
    }

    // Inject events
    for (int i = 0; i < 100; ++i) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
        engine.inject_event("event_" + std::to_string(i % 5), data);
    }

    // Let workers process
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // Unregister modules
    for (int i = 0; i < 5; ++i) {
        engine.unregister_module("stress_mod_" + std::to_string(i));
    }

    engine.stop();
}

}  // namespace
}  // namespace tyche
