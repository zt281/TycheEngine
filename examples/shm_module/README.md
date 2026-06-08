# Shared Memory Module Example

This example demonstrates how to write a DLL/SO module that communicates
with Tyche Engine via shared memory queues.

## Architecture

```
+---------------+      shared memory      +------------------+
| DLL/SO Module |  <===================>  |  SharedMemoryBridge |
| (this example)|      queue              |    (in engine)   |
+---------------+                         +--------+---------+
                                                   |
                                                   | ZMQ
                                                   v
                                          +--------+---------+
                                          |   TycheEngine    |
                                          |  (XPUB/XSUB)     |
                                          +------------------+
```

## Message Format

Messages on the shared-memory queue use a simple prefix protocol:

```
[uint16_t topic_len (LE)] [char topic[topic_len]] [uint8_t payload[]]
```

- `topic_len`: length of the topic string in little-endian
- `topic`: UTF-8 topic name (e.g., "tick", "quote")
- `payload`: message payload (typically msgpack-serialized `tyche::Message`)

## Writing a Module

A DLL/SO module must export four functions:

```c
int  tyche_module_init(const char* shm_queue_name);
int  tyche_module_run(void);
void tyche_module_stop(void);
const char* tyche_module_get_interfaces(void);
```

See `example_module.cpp` for a complete example.

## Configuration

Add `shm_modules` and/or `shm_bridges` to the engine config file:

```json
{
  "shm_modules": [
    {
      "library_path": "path/to/module.dll",
      "shm_queue_name": "tyche_shm_my_module",
      "zmq_topics": ["tick", "order"]
    }
  ],
  "shm_bridges": [
    {
      "shm_queue_name": "tyche_shm_external",
      "zmq_topic": "market_data"
    }
  ]
}
```

### `shm_modules`

- `library_path`: path to the DLL/SO file
- `shm_queue_name`: shared memory queue name (engine creates it, module opens it)
- `zmq_topics`: static topic mapping; all messages from this module are forwarded
  to these ZMQ topics. If empty, the topic is extracted from each message's prefix.

### `shm_bridges`

For external processes that write to a shared memory queue directly (without
a DLL/SO module):

- `shm_queue_name`: shared memory queue name (engine creates it)
- `zmq_topic`: ZMQ topic to forward messages to

## Running

```bash
# Build the engine
cd build
cmake --build . --target tyche_engine

# Build the example module (Windows)
cl /LD examples/shm_module/example_module.cpp /Feexample_module.dll

# Run the engine with config
./bin/Release/tyche_engine.exe --config examples/shm_module/config.json
```

## API Reference

### `SharedMemoryQueue` (C++)

```cpp
tyche::SharedMemoryQueue queue(
    {"queue_name", slot_count=1024, max_msg_size=65536},
    owner=true   // engine sets true, module sets false
);

// Write
std::vector<uint8_t> data = ...;
bool ok = queue.write(data);

// Read
auto result = queue.read();
if (result.has_value()) {
    std::vector<uint8_t>& msg = result.value();
    // process message
}
```

### `DynamicLibrary` (C++)

```cpp
tyche::DynamicLibrary lib("path/to/module.dll");
if (lib.is_loaded()) {
    auto fn = lib.get_function<int(const char*)>("tyche_module_init");
    if (fn) fn("queue_name");
}
```
