#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// ═══════════════════════════════════════════════════════════════════════
// Tyche Shared-Memory Module Interface
// ═══════════════════════════════════════════════════════════════════════
//
// DLL/SO modules loaded by TycheEngine via the SharedMemoryBridge must
// implement these functions.  The module communicates with the engine
// through a named shared-memory queue instead of ZMQ sockets.
//
// Message format on the shared-memory queue:
//   [uint16_t topic_len] [char topic[topic_len]] [uint8_t payload[...]]
//
//   topic_len  : little-endian uint16_t
//   topic      : UTF-8 topic string
//   payload    : msgpack-serialized tyche::Message (or user-defined bytes)
//
// The engine reads from the queue, extracts the topic, and forwards the
// payload to the corresponding ZMQ topic.

// ── Module lifecycle ────────────────────────────────────────────────

// Initialize the module.
// @param shm_queue_name  Name of the shared-memory queue to use.
//                        The module opens this queue (owner=false).
// @return 0 on success, non-zero on error.
typedef int (*tyche_module_init_fn)(const char* shm_queue_name);

// Start the module.  Blocks until the module is stopped.
// @return 0 on success, non-zero on error.
typedef int (*tyche_module_run_fn)(void);

// Stop the module.  Must cause tyche_module_run to return promptly.
typedef void (*tyche_module_stop_fn)(void);

// Get module interface declarations as a JSON string.
// Format: [{"name":"on_tick","pattern":"on","event_type":"tick"},...]
// The returned pointer must remain valid for the module's lifetime.
typedef const char* (*tyche_module_get_interfaces_fn)(void);

// ── Symbol names ────────────────────────────────────────────────────

#define TYCHE_MODULE_INIT_NAME           "tyche_module_init"
#define TYCHE_MODULE_RUN_NAME            "tyche_module_run"
#define TYCHE_MODULE_STOP_NAME           "tyche_module_stop"
#define TYCHE_MODULE_GET_INTERFACES_NAME "tyche_module_get_interfaces"

#ifdef __cplusplus
}
#endif
