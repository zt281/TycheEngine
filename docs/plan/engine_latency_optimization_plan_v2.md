# TycheEngine C++ 引擎延迟优化实施计划

## 项目状态与上下文

**分析日期：** 2026-06-13

**当前架构：** TycheEngine C++ 引擎已具备部分优化基础设施：
- `FlatMessageHeader` / `FlatQuoteTick` 已定义（`src/tyche/cpp/flat_message.h`）
- `StringIntern` 已存在，用于 topic/module_id 的 uint32_t 化
- `ShardedTopicQueueMap` 已使用 bucket spinlock 替代全局 mutex
- `Frame` 已具备 64B SSO（小对象内联优化）
- `RingBuffer` 已是 lock-free MPSC 实现
- `SharedMemoryQueue` 已支持跨进程 SPSC 通信
- `SharedMemoryBridge` 已支持 DLL/SO 模块加载和桥接

**关键瓶颈（已确认）：**
1. `flat_serializer.h` 被 `test_flat_message.cpp` 引用但从未创建，FlatMessage 无法实际使用
2. `_enqueue_from_xsub()` 每帧仍构造 `std::string topic` + `std::vector<Frame>`
3. `event_egress_worker()` 使用 `condition_variable::wait_for(1s)`，唤醒延迟 ~2-5 μs
4. `_now()` 使用 `system_clock::now()` 系统调用，每次 ~25 ns
5. `SharedMemoryBridge::_forward_to_zmq()` 仍走 msgpack 序列化路径
6. CTP Gateway `option_dispatch_loop()` 使用 `sleep_for(1ms)` 轮询
7. `serialize()` 返回 `std::vector<uint8_t>`，每次触发堆分配

**用户决策：**
- 实施策略：保守逐步实施（P0→P1→P2→P3）
- 兼容性策略：编译宏 + 配置开关控制，默认关闭优化，手动启用
- 目标平台：跨平台双支持（Windows MSVC + Linux GCC/Clang）

---

## 优化目标

| 场景 | 优化前 | 优化后 (P0+P1) | 优化后 (全部) |
|------|--------|----------------|---------------|
| CTP行情→Engine (同机) | 25-50 μs | 200-500 ns | 50-200 ns |
| Engine→Module (同机 C++) | 20-40 μs | 100-300 ns | 30-100 ns |
| Engine→Module (Python) | 25-50 μs | 20-40 μs (不变) | 15-30 μs (ipc) |
| 完整链路 (C++ 全路径) | 50-100 μs | 500 ns - 1 μs | 100-500 ns |

---

## Phase 1: P0 核心优化（端到端延迟降低 100x+）

### Task P0.1: 创建 `flat_serializer.h`（零拷贝序列化）

**问题：** `tests/cpp/test_flat_message.cpp` 引用 `tyche/cpp/flat_serializer.h`，但该文件从未创建，导致 FlatMessage 基础设施无法实际使用。

**目标：** 提供 `serialize_flat()` / `deserialize_flat()` 实现，使现有测试通过编译，并为后续 C++ 模块间快速路径提供基础。

**文件变更：**
- **新建** `src/tyche/cpp/flat_serializer.h`

**API 设计：**
```cpp
namespace tyche {

// Serialize Message into caller-provided buffer. Returns bytes written, or 0 on overflow.
// All operations are noexcept; no heap allocation.
size_t serialize_flat(const Message& msg, uint8_t* buffer, size_t capacity) noexcept;

// Deserialize FlatMessage bytes into Message. Payload stored as raw bytes in msg.payload["__flat__"].
// Returns Message with msg_type=COMMAND on error (empty input or invalid header).
Message deserialize_flat(const uint8_t* data, size_t size) noexcept;

// Serialize a FlatQuoteTick directly into a ZMQ-compatible frame buffer.
// Returns bytes written (always sizeof(FlatQuoteTick) on success, 0 on misalignment).
size_t serialize_flat_quote(const FlatQuoteTick& tick, uint8_t* buffer, size_t capacity) noexcept;

// Deserialize FlatQuoteTick from raw bytes (zero-copy pointer cast).
// Returns nullptr if size < sizeof(FlatQuoteTick) or alignment is wrong.
const FlatQuoteTick* deserialize_flat_quote(const uint8_t* data, size_t size) noexcept;

} // namespace tyche
```

**实现要点：**
- `serialize_flat` 直接写入 `buffer`，不分配堆内存
- `payload` 区域使用简化 msgpack 编码（保持与现有 msgpack 的兼容性边界）
- 所有函数标记 `noexcept`
- `deserialize_flat` 的 payload 以 `std::vector<uint8_t>` 存储在 `msg.payload["__flat__"]` 中，供后续处理

**验证：**
- `tests/cpp/test_flat_message.cpp` 现有 14 个测试用例全部通过
- 新增 `static_assert` 验证 `serialize_flat` 对空 sender/event 的处理

**兼容性：** 纯新增文件，不影响现有 msgpack 路径。通过 `TYCHE_OPT_FLAT_MSG` 编译宏控制启用。

---

### Task P0.2: `SharedMemoryBridge` 零拷贝直通路径

**问题：** `SharedMemoryBridge::_forward_to_zmq()`（`shared_memory_bridge.cpp:287-301`）将 SHM 消息包装为 `Message` 后调用 `serialize(msg)`，再调用 `inject_event()`。这引入了完整的 msgpack 序列化开销（~800-1200 ns），而 SHM 消息本身已是原始字节。

**目标：** 新增 `inject_event_raw()` 绕过 msgpack，直接透传原始字节到 topic queue。

**文件变更：**
- `src/tyche/cpp/engine/engine.h` — 新增 `inject_event_raw()` 声明
- `src/tyche/cpp/engine/engine.cpp` — 实现 `inject_event_raw()`
- `src/tyche/cpp/engine/shared_memory_bridge.cpp` — 修改 `_forward_to_zmq()` 使用 raw path

**API 设计：**
```cpp
// engine.h 中新增
class TycheEngine {
public:
    // Inject raw bytes directly into topic queues (zero-copy, no msgpack).
    // Used by SharedMemoryBridge to bypass serialization overhead.
    void inject_event_raw(const std::string& topic, const uint8_t* data, size_t size);
};
```

**实现要点：**
- `inject_event_raw()` 直接构造 `Frame` 并入队，跳过 `Message` 构造和 `serialize()`
- 唤醒 egress worker 使用 `memory_order_release` 存储 flag（替代 mutex + cv）
- `_forward_to_zmq()` 直接调用 `inject_event_raw(topic, payload.data(), payload.size())`

**验证：**
- 现有 `test_shared_memory_queue.cpp` 通过
- 新增 benchmark `tests/perf/shm_bridge_bench.cpp` 对比 msgpack vs raw 注入延迟

**兼容性：** `inject_event()` 保留不变；新增 `inject_event_raw()` 仅用于 C++ 内部路径。通过 `TYCHE_OPT_SHM_DIRECT` 编译宏控制启用。

---

### Task P0.3: `_enqueue_from_xsub()` 热路径优化

**问题：** 当前实现（`engine.cpp:277-297`）每帧构造 `std::string topic`（堆分配）和 `std::vector<Frame> fframes`（堆分配），且 `get_or_create()` 返回 `shared_ptr<TopicQueue>` 触发原子引用计数。

**目标：** 消除热路径上的所有堆分配和引用计数操作。

**文件变更：**
- `src/tyche/cpp/engine/engine.cpp` — 修改 `_enqueue_from_xsub()`
- `src/tyche/cpp/engine/sharded_topic_map.h` — 新增 `get_raw()` 接口
- `src/tyche/cpp/engine/sharded_topic_map.cpp` — 实现 `get_raw()`

**优化方案：**
```cpp
void TycheEngine::_enqueue_from_xsub(
    const std::vector<std::vector<uint8_t>>& frames) {
    if (frames.size() < 2) return;

    // 1. string_view 提取 topic（零分配）
    std::string_view topic_sv(
        reinterpret_cast<const char*>(frames[0].data()), frames[0].size());

    // 2. InternId 快速查找（避免字符串哈希）
    InternId topic_id = _intern.lookup(topic_sv);
    if (topic_id == INVALID_INTERN_ID) {
        // 冷路径：首次出现的 topic，创建队列并注册索引
        topic_id = _intern.intern(std::string(topic_sv));
        _topic_queues.get_or_create(std::string(topic_sv), static_cast<size_t>(_queue_capacity));
    }

    // 3. 直接获取 TopicQueue 裸指针（避免 shared_ptr 引用计数）
    TopicQueue* q = _topic_queues.get_raw(topic_id);
    if (!q) return;

    // 4. 栈上 Frame 数组（零分配）
    static constexpr size_t MAX_FRAMES = 4;
    Frame fixed_frames[MAX_FRAMES];
    size_t n = std::min(frames.size(), MAX_FRAMES);
    for (size_t i = 0; i < n; ++i) {
        fixed_frames[i] = Frame(frames[i].data(), frames[i].size());
    }

    // 5. 入队（使用 FastClock，见 P1.2）
    q->put(QueueItem(FastClock::now(), std::vector<Frame>(fixed_frames, fixed_frames + n)));

    // 6. 无锁唤醒（见 P1.1）
    _egress_wakeup_flag.store(true, std::memory_order_release);
}
```

**依赖：** P1.1（无锁唤醒）、P1.2（FastClock）

**验证：**
- `tests/perf/topic_queue_bench.cpp` 对比优化前后
- 现有 `tests/cpp/test_topic_queue.cpp` 通过

**兼容性：** 仅修改 C++ Engine 内部路径；Python 侧不受影响。通过 `TYCHE_OPT_ENQUEUE_FAST` 编译宏控制启用。

---

## Phase 2: P1 高优先级优化（延迟降低 3-30x）

### Task P1.1: Egress Worker 自适应轮询（替代 condition_variable）

**问题：** `event_egress_worker()`（`engine.cpp:990-1023`）使用 `condition_variable::wait_for(1s)`，唤醒延迟 ~2-5 μs。在高频场景下，事件到达间隔远小于 1s，CV 成为瓶颈。

**目标：** 消除 CV 唤醒延迟，使用自适应 spin/yield/sleep 策略。

**文件变更：**
- **新建** `src/tyche/cpp/engine/adaptive_spin.h`
- `src/tyche/cpp/engine/engine.cpp` — 修改 `_event_egress_worker()`

**API 设计：**
```cpp
// src/tyche/cpp/engine/adaptive_spin.h
namespace tyche {

class AdaptiveSpin {
public:
    explicit AdaptiveSpin(int spin_threshold = 1000,
                          int yield_threshold = 10000,
                          int sleep_us = 10) noexcept;

    // Call when work was found. Resets idle counter.
    void reset() noexcept;

    // Call when no work was found. Performs appropriate wait.
    void wait() noexcept;

private:
    int _idle_count = 0;
    int _spin_threshold;
    int _yield_threshold;
    int _sleep_us;
};

} // namespace tyche
```

**Engine 集成：**
```cpp
void TycheEngine::_event_egress_worker() {
    AdaptiveSpin spinner(1000, 10000, 10);
    while (_running.load(std::memory_order_relaxed)) {
        auto queues = _topic_queues.snapshot();
        bool had_work = false;
        for (auto& [topic, q] : queues) {
            while (_running.load(std::memory_order_relaxed)) {
                auto item = q->get();
                if (!item.has_value()) break;
                had_work = true;
                spinner.reset();
                // ... process item (TTL check, dead letter) ...
            }
        }
        if (!had_work) {
            spinner.wait();
        }
    }
}
```

**平台适配：**
- Windows: `_mm_pause()` (MSVC intrinsic)
- Linux x86: `__builtin_ia32_pause()` (GCC/Clang)
- Linux ARM: `__asm__ __volatile__("yield" :::)`

**验证：**
- 新增 `tests/cpp/test_adaptive_spin.cpp`（验证 spin/yield/sleep 状态转换）
- 基准测试对比 CV 唤醒 vs 自适应轮询的延迟分布

**兼容性：** 纯 C++ 内部优化；Python 引擎不受影响。通过 `TYCHE_OPT_ADAPTIVE_SPIN` 编译宏控制启用。

---

### Task P1.2: FastClock（RDTSC 缓存时间戳）

**问题：** `_now()`（`engine.cpp:58-61`）每次调用 `system_clock::now()` + `duration_cast`，系统调用开销 ~25 ns。热路径（`_enqueue_from_xsub`、`event_egress_worker`、heartbeat）每秒调用数万次。

**目标：** 将时间戳获取降至 ~3 ns，使用 RDTSC + 周期性校准。

**文件变更：**
- **新建** `src/tyche/cpp/engine/fast_clock.h`

**API 设计：**
```cpp
// src/tyche/cpp/engine/fast_clock.h
namespace tyche {

class FastClock {
public:
    // Fast path: read cached timestamp (updated by background thread every 1ms).
    // Uses memory_order_relaxed; suitable for enqueue_time, TTL checks.
    static double now() noexcept;

    // Precise path: RDTSC-based calculation with cached tsc_to_ns ratio.
    // Slightly slower (~10 ns) but more accurate between calibration ticks.
    static double now_precise() noexcept;

    // Start background calibration thread. Call in Engine::start_nonblocking().
    static void start_calibration();

    // Stop background calibration thread. Call in Engine::stop().
    static void stop_calibration();

    // Force immediate calibration. Useful after thread affinity changes.
    static void calibrate() noexcept;
};

} // namespace tyche
```

**实现要点：**
- 后台线程每 1ms 用 `QueryPerformanceCounter()` (Windows) / `clock_gettime(CLOCK_MONOTONIC)` (Linux) 更新缓存时间戳
- `now()` 读取 `std::atomic<double>` 缓存值，使用 `memory_order_relaxed`
- `now_precise()` 使用 `__rdtsc()` (x86) / `cntvct_el0` (ARM) 计算差值
- 首次调用时校准 `tsc_to_ns` 比率；运行时检测 CPU 频率变化并自动重新校准

**验证：**
- 新增 `tests/cpp/test_fast_clock.cpp`（验证 `now()` 与 `system_clock::now()` 偏差 < 2ms）
- 基准测试对比调用延迟

**兼容性：** 替换 `TycheEngine::_now()` 实现；不影响外部接口。通过 `TYCHE_OPT_FAST_CLOCK` 编译宏控制启用。

---

### Task P1.3: QueueItem 对象池

**问题：** `QueueItem` 的 `std::vector<Frame> frames` 每次构造/析构都触发堆分配（vector 元数据分配）。在高吞吐场景下，每秒数万次分配成为 GC 压力。

**目标：** 使用固定大小对象池复用 `QueueItem`，消除堆分配。

**文件变更：**
- **新建** `src/tyche/cpp/engine/object_pool.h`
- `src/tyche/cpp/engine/topic_queue.h` — 新增 `put_ptr()` / `get_ptr()` 接口
- `src/tyche/cpp/engine/topic_queue.cpp` — 实现 `put_ptr()` / `get_ptr()`
- `src/tyche/cpp/engine/engine.cpp` — 集成对象池到 `_enqueue_from_xsub()`

**API 设计：**
```cpp
// src/tyche/cpp/engine/object_pool.h
namespace tyche {

template <typename T, size_t PoolSize = 65536>
class ObjectPool {
public:
    ObjectPool() noexcept;
    ~ObjectPool() noexcept;

    // Acquire an object from the pool. Returns nullptr if pool exhausted.
    T* acquire() noexcept;

    // Release an object back to the pool. Object must have been acquired from this pool.
    void release(T* obj) noexcept;

    size_t available() const noexcept;
    size_t total() const noexcept { return PoolSize; }

private:
    struct alignas(64) Slot {
        std::atomic<Slot*> next;
        alignas(alignof(T)) uint8_t storage[sizeof(T)];
    };
    std::atomic<Slot*> _free_list;
    std::vector<Slot> _slots;
};

} // namespace tyche
```

**TopicQueue 扩展：**
```cpp
class TopicQueue {
public:
    // Existing put/get remain unchanged
    bool put(QueueItem item);
    std::optional<QueueItem> get();

    // New: pointer-based interface for pool-backed items
    bool put_ptr(QueueItem* item) noexcept;
    QueueItem* get_ptr() noexcept;  // Returns nullptr if empty; caller must release to pool
};
```

**验证：**
- 新增 `tests/cpp/test_object_pool.cpp`（验证 acquire/release 正确性、无内存泄漏）
- 压力测试：多线程 MPSC 场景下验证无数据竞争
- ASAN/Valgrind 验证无内存泄漏

**兼容性：** 新增 `put_ptr`/`get_ptr` 接口；原有 `put`/`get` 保留。通过 `TYCHE_OPT_OBJECT_POOL` 编译宏控制启用。

---

### Task P1.4: TopicQueueIndex（基于 InternId 的 O(1) 索引）

**问题：** `ShardedTopicQueueMap` 使用字符串哈希 + bucket spinlock，热路径仍有 ~40 ns 的哈希计算和锁竞争。

**目标：** 对已注册 topic 使用 `InternId` 直接数组索引，O(1) 查找，无锁。

**文件变更：**
- **新建** `src/tyche/cpp/engine/topic_queue_index.h`
- `src/tyche/cpp/engine/engine.h` — 新增 `_topic_queue_index` 字段
- `src/tyche/cpp/engine/engine.cpp` — 在 `register_module()` 中同步更新索引

**API 设计：**
```cpp
// src/tyche/cpp/engine/topic_queue_index.h
namespace tyche {

class TopicQueueIndex {
public:
    // Get queue by InternId. Returns nullptr if not found.
    TopicQueue* get(InternId id) const noexcept;

    // Register a queue for an InternId. Thread-safe (used at registration time).
    void set(InternId id, TopicQueue* q) noexcept;

    // Snapshot all (id, queue) pairs for egress worker.
    std::vector<std::pair<InternId, TopicQueue*>> snapshot() const;

private:
    std::vector<TopicQueue*> _queues;  // index = InternId
    mutable std::mutex _resize_lock;   // only for resizing
};

} // namespace tyche
```

**集成方式：**
- `ShardedTopicQueueMap` 保留用于冷路径（topic 创建、GC、admin 查询）
- `TopicQueueIndex` 用于热路径（`_enqueue_from_xsub` 和 `event_egress_worker`）
- 在 `register_module()` 中创建 topic queue 时同步调用 `_topic_queue_index.set(topic_id, q.get())`

**验证：**
- 新增 `tests/cpp/test_topic_queue_index.cpp`（验证 `get`/`set` 一致性）
- 集成到 `topic_queue_bench.cpp` 中对比 string map vs array index

**兼容性：** 纯新增，不影响现有 API。通过 `TYCHE_OPT_TOPIC_INDEX` 编译宏控制启用。

---

### Task P1.5: CTP Gateway QuoteTick 缓存行对齐

**问题：** 当前 `QuoteTick` 结构未显式对齐，可能跨多个缓存行边界，导致 false sharing。CTP 行情回调线程和 option dispatch 线程访问同一结构的不同字段时，缓存一致性协议产生额外开销。

**目标：** 显式对齐到 64 字节缓存行，将热字段和冷字段分离到不同缓存行。

**文件变更：**
- `src/modules/ctp_gateway_cpp/src/quote_tick.h` — 重构内存布局

**优化方案：**
```cpp
#pragma pack(push, 1)
struct alignas(64) QuoteTick {
    // Hot fields — first cache line (64 bytes)
    char     instrument_id[32];     // 32 bytes
    double   last_price;            // 8 bytes
    double   bid_price1;            // 8 bytes
    double   ask_price1;            // 8 bytes
    int32_t  bid_volume1;            // 4 bytes
    int32_t  ask_volume1;            // 4 bytes
    // Total: 64 bytes

    // Cold fields — second cache line (64 bytes)
    double   open_interest;         // 8 bytes
    double   turnover;             // 8 bytes
    double   upper_limit_price;    // 8 bytes
    double   lower_limit_price;    // 8 bytes
    double   open_price;            // 8 bytes
    double   high_price;            // 8 bytes
    double   low_price;             // 8 bytes
    double   pre_settle_price;     // 8 bytes
    // Total: 64 bytes

    // Third cache line
    char     update_time[16];      // 16 bytes
    char     exchange_id[16];      // 16 bytes
    char     trading_day[16];      // 16 bytes
    int      volume;                // 4 bytes
    int      update_millisec;      // 4 bytes
    uint64_t receive_ts_ns;        // 8 bytes
    uint32_t sequence;             // 4 bytes
    uint8_t  flags;                 // 1 byte
    uint8_t  _pad[3];              // 3 bytes
    // Total: 64 bytes
};
#pragma pack(pop)

static_assert(sizeof(QuoteTick) == 192, "QuoteTick must be 192 bytes (3 cache lines)");
static_assert(alignof(QuoteTick) == 64, "QuoteTick must be aligned to 64 bytes");
```

**验证：**
- 现有 `test_option_dispatch.cpp` 通过
- 新增 `static_assert` 验证大小和布局

**兼容性：** 纯内存布局变更；不影响序列化/反序列化（CTP gateway 内部使用）。无需编译宏，直接应用。

---

## Phase 3: P2 中等优先级优化（延迟降低 3-10x）

### Task P2.1: RCU 订阅表快照

**问题：** 事件分发和 job 路由时读取 subscriber/handler 列表需要 `shared_lock` 或 `unique_lock` 保护 `_modules_lock`，锁竞争在模块数量增加时恶化。

**目标：** 使用 Read-Copy-Update (RCU) 模式实现无锁读路径。

**文件变更：**
- `src/tyche/cpp/engine/engine.h` — 替换原有订阅表为 RCU 快照
- `src/tyche/cpp/engine/engine.cpp` — 修改 `register_module()` / `unregister_module()` / job worker

**API 设计：**
```cpp
// engine.h 中替换原有订阅表
struct SubscriptionSnapshot {
    std::unordered_map<InternId, std::vector<std::string>> topic_subscribers;
    std::unordered_map<InternId, std::vector<std::string>> topic_producers;
    std::unordered_map<InternId, std::vector<std::string>> job_handlers;
};

// Engine 持有 atomic<shared_ptr>：
std::atomic<std::shared_ptr<SubscriptionSnapshot>> _subscription_snapshot;
```

**实现要点：**
- 读路径（热路径）：`auto snap = _subscription_snapshot.load(std::memory_order_acquire);` 无锁
- 写路径（冷路径）：copy-on-write，修改后原子替换
- 适用于 job router worker 和 event egress worker 中的订阅表查询

**验证：**
- 新增 `tests/cpp/test_rcu_snapshot.cpp`（并发 stress test，10M+ 操作）
- TSAN 验证无数据竞争

**兼容性：** 内部数据结构变更；不影响外部接口。通过 `TYCHE_OPT_RCU_SNAPSHOT` 编译宏控制启用。

---

### Task P2.2: TLS 序列化缓冲区

**问题：** `serialize()`（`message.cpp:125`）每次返回 `std::vector<uint8_t>`，触发堆分配 + memcpy。在高频发送场景下，每秒数万次分配。

**目标：** 提供线程局部缓冲区接口，消除堆分配。

**文件变更：**
- `src/tyche/cpp/message.h` — 新增 `serialize_tls()` / `serialize_into()` 声明
- `src/tyche/cpp/message.cpp` — 实现 TLS 缓冲区路径

**API 设计：**
```cpp
// message.h 中新增
namespace tyche {

// Buffer view referencing thread-local storage. Valid only until next serialize_tls call.
struct BufferView {
    const uint8_t* data;
    size_t size;
};

// Serialize into thread-local buffer. Zero heap allocation. Not thread-safe across calls.
BufferView serialize_tls(const Message& msg) noexcept;

// Serialize into caller-provided buffer. Returns bytes written, or 0 on overflow.
size_t serialize_into(const Message& msg, uint8_t* buffer, size_t capacity) noexcept;

} // namespace tyche
```

**实现要点：**
- `thread_local static msgpack::sbuffer tls_buffer(4096);`
- `serialize_tls()` 复用 `tls_buffer`，返回 `BufferView`
- 调用者需在下次调用前使用完数据（典型场景：立即发送 ZMQ frame）

**验证：**
- 基准测试对比 `serialize()` vs `serialize_tls()` 延迟
- 线程安全测试：多线程并发调用验证隔离性

**兼容性：** 新增接口；原有 `serialize()` 保留用于 Python 互操作。通过 `TYCHE_OPT_TLS_BUFFER` 编译宏控制启用。

---

### Task P2.3: CTP Gateway 批量分发 + 自适应轮询

**问题：** `option_dispatch_loop()`（`ctp_gateway.cpp:428-491`）每次只弹出一个 tick，然后 `sleep_for(1ms)`。在高吞吐场景下，1ms 睡眠导致大量延迟；且单条发送无法利用 batching 优势。

**目标：** 批量弹出 + 自适应 spin/yield/sleep，消除 1ms 睡眠延迟。

**文件变更：**
- `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp` — 修改 `option_dispatch_loop()`
- `src/tyche/cpp/module.h` — 新增 `send_event_flat()` 声明（依赖 P0.1）
- `src/tyche/cpp/module.cpp` — 实现 `send_event_flat()`

**优化方案：**
```cpp
void CtpGateway::option_dispatch_loop() {
    int idle_spins = 0;
    constexpr int BATCH_SIZE = 64;

    while (ctp_running_.load(std::memory_order_relaxed)) {
        // 批量弹出
        QuoteTick batch[BATCH_SIZE];
        size_t n = 0;
        while (n < BATCH_SIZE) {
            auto tick = option_ring_buffer_.pop();
            if (!tick.has_value()) break;
            batch[n++] = std::move(*tick);
        }

        if (n > 0) {
            idle_spins = 0;
            for (size_t i = 0; i < n; ++i) {
                // 使用 flat path 发送（P0.1 + P2.4）
                send_event_flat("send_compute_greeks", batch[i]);
            }
        } else {
            // 自适应等待
            if (++idle_spins < 1000) {
                _mm_pause();
            } else if (idle_spins < 100000) {
                std::this_thread::yield();
            } else {
                std::this_thread::sleep_for(std::chrono::microseconds(100));
            }
        }
    }
}
```

**验证：**
- 现有 `test_option_dispatch.cpp` 通过
- 新增 benchmark `tests/perf/ctp_dispatch_bench.cpp` 对比单条 vs 批量发送吞吐量

**兼容性：** 仅修改 CTP gateway 内部；不影响 Engine 接口。通过 `TYCHE_OPT_CTP_BATCH` 编译宏控制启用。

---

### Task P2.4: `send_event_flat()` 快速路径（TycheModule）

**问题：** C++ 模块间发送 `FlatQuoteTick` 仍需经过 `Message` 构造、`Payload` 填充、`serialize()`，完整 msgpack 开销。

**目标：** 直接通过 PUB socket 发送 `FlatQuoteTick` 的原始字节，跳过所有中间层。

**文件变更：**
- `src/tyche/cpp/module.h` — 新增 `send_event_flat()` 声明
- `src/tyche/cpp/module.cpp` — 实现 `send_event_flat()`

**API 设计：**
```cpp
class TycheModule {
public:
    // Send flat binary event (C++ module-to-module only, no Python interop).
    // Directly sends FlatQuoteTick bytes via PUB socket, bypassing msgpack.
    void send_event_flat(const std::string& event, const FlatQuoteTick& tick);

    // Generic flat binary send for custom flat structs.
    void send_event_flat(const std::string& event, const uint8_t* data, size_t size);
};
```

**实现要点：**
- 直接通过 PUB socket 发送 `FlatQuoteTick` 的 `memcpy` 数据
- 在 ZMQ topic frame 中标记 flat binary 格式（topic 前缀 `__flat__:`）
- Engine 侧的 `event_proxy_worker` 识别 `__flat__:` 前缀，直接透传不反序列化

**验证：**
- 端到端测试：C++ module A 发送 FlatQuoteTick -> Engine -> C++ module B 接收
- 与 msgpack 路径数据一致性验证

**兼容性：** 新增接口；原有 `send_event()` 保留用于 Python 互操作。通过 `TYCHE_OPT_FLAT_MSG` 编译宏控制启用（与 P0.1 共用同一宏）。

---

## Phase 4: P3 低优先级优化（可选）

### Task P3.1: CPU 亲和性绑定

**目标：** 将关键线程（event_proxy、event_egress）绑定到专用 CPU 核，减少缓存失效和上下文切换。

**文件变更：**
- **新建** `src/tyche/cpp/engine/thread_affinity.h`

**API 设计：**
```cpp
namespace tyche {

// Set thread affinity to a specific CPU core. Returns false on failure.
bool set_thread_affinity(std::thread& t, int cpu_core);

// Set affinity for current thread.
bool set_thread_affinity_current(int cpu_core);

// Get current CPU core index.
int get_current_cpu() noexcept;

} // namespace tyche
```

**平台适配：**
- Windows: `SetThreadAffinityMask()`
- Linux: `pthread_setaffinity_np()`

**验证：**
- 新增 `tests/cpp/test_thread_affinity.cpp`

**兼容性：** 纯新增，默认不启用。通过 `TYCHE_OPT_CPU_AFFINITY` 编译宏和 `EngineConfig` 配置控制。

---

### Task P3.2: 性能基准测试套件完善

**目标：** 为所有优化提供量化验证手段。

**文件变更：**
- **新建** `tests/perf/flat_message_bench.cpp`
- **新建** `tests/perf/shm_bridge_bench.cpp`
- **新建** `tests/perf/e2e_latency_bench.cpp`
- **新建** `tests/perf/alloc_bench.cpp`
- `tests/cpp/CMakeLists.txt` — 新增 benchmark target
- `src/tyche/cpp/CMakeLists.txt` — 新增 benchmark target

**基准测试内容：**

| 文件 | 测量内容 |
|------|----------|
| `flat_message_bench.cpp` | FlatMessage vs msgpack serialize/deserialize 对比 |
| `shm_bridge_bench.cpp` | SHM bridge raw vs msgpack 注入延迟 |
| `e2e_latency_bench.cpp` | 完整链路：CTP模拟→Engine→Module 端到端延迟分布 |
| `alloc_bench.cpp` | 热路径内存分配统计（ObjectPool vs malloc） |

**验证：**
- 所有 benchmark 在 Release 模式下编译运行
- 输出 p50/p99/p999 延迟分布

---

## 编译宏与配置开关

### CMake 选项

```cmake
# src/tyche/cpp/CMakeLists.txt 中新增
option(TYCHE_OPT_FLAT_MSG "Enable FlatMessage fast path for C++ module interop" OFF)
option(TYCHE_OPT_SHM_DIRECT "Enable SharedMemory raw direct path" OFF)
option(TYCHE_OPT_ENQUEUE_FAST "Enable fast _enqueue_from_xsub with zero-allocation" OFF)
option(TYCHE_OPT_ADAPTIVE_SPIN "Enable adaptive spin for egress worker" OFF)
option(TYCHE_OPT_FAST_CLOCK "Enable RDTSC-based FastClock" OFF)
option(TYCHE_OPT_OBJECT_POOL "Enable ObjectPool for QueueItem reuse" OFF)
option(TYCHE_OPT_TOPIC_INDEX "Enable InternId-based TopicQueueIndex" OFF)
option(TYCHE_OPT_RCU_SNAPSHOT "Enable RCU subscription snapshot" OFF)
option(TYCHE_OPT_TLS_BUFFER "Enable TLS buffer for serialization" OFF)
option(TYCHE_OPT_CTP_BATCH "Enable CTP option batch dispatch" OFF)
option(TYCHE_OPT_CPU_AFFINITY "Enable CPU affinity binding" OFF)

# 传递编译宏
target_compile_definitions(tyche_engine PRIVATE
    $<$<BOOL:${TYCHE_OPT_FLAT_MSG}>:TYCHE_OPT_FLAT_MSG>
    $<$<BOOL:${TYCHE_OPT_SHM_DIRECT}>:TYCHE_OPT_SHM_DIRECT>
    ...
)
```

### 运行时配置

```cpp
// engine.h 中新增
struct EngineConfig {
    bool use_flat_message = false;
    bool use_shm_direct = false;
    bool use_enqueue_fast = false;
    bool use_adaptive_spin = false;
    bool use_fast_clock = false;
    bool use_object_pool = false;
    bool use_topic_index = false;
    bool use_rcu_snapshot = false;
    bool use_tls_buffer = false;
    bool use_cpu_affinity = false;

    // CPU affinity settings (only used if use_cpu_affinity = true)
    int event_proxy_core = -1;
    int event_egress_core = -1;
};

// 新增构造函数重载
TycheEngine(Endpoint registration_endpoint, ..., EngineConfig config = {});
```

---

## Python 互操作兼容性保证

### 核心原则

**所有优化均为 C++ 内部路径的 opt-in，Python 通信路径完全不受影响。**

### 通信路径矩阵

| 通信路径 | 序列化格式 | 传输方式 | 优化影响 |
|----------|------------|----------|----------|
| Python Module → Engine | msgpack | ZMQ tcp:// | **无影响** |
| Engine → Python Module | msgpack | ZMQ tcp:// | **无影响** |
| C++ Module → Engine (默认) | msgpack | ZMQ tcp:// | **无影响** |
| C++ Module → Engine (fast) | FlatMessage | ZMQ inproc:// / SHM | **新增快速路径** |
| CTP Gateway → Engine (默认) | msgpack | ZMQ tcp:// | **无影响** |
| CTP Gateway → Engine (fast) | FlatQuoteTick | SharedMemoryQueue | **新增快速路径** |

### 回退机制

- 编译时：通过 CMake 选项关闭所有优化，回退到原始代码路径
- 运行时：通过 `EngineConfig` 配置开关选择性启用/禁用
- 性能劣化超过 5% 的优化不合入

---

## 验证策略矩阵

| 任务 | 单元测试 | 基准测试 | 集成测试 | 特殊验证 |
|------|----------|----------|----------|----------|
| P0.1 flat_serializer | `test_flat_message.cpp` (现有) | `flat_message_bench.cpp` | 端到端 round-trip | 字节级一致性 |
| P0.2 SHM bridge raw | `test_shared_memory_queue.cpp` | `shm_bridge_bench.cpp` | Engine + Bridge 链路 | TSAN 无数据竞争 |
| P0.3 _enqueue优化 | `test_topic_queue.cpp` | `topic_queue_bench.cpp` | 10 worker 全链路 | 现有测试全部通过 |
| P1.1 adaptive_spin | `test_adaptive_spin.cpp` (新增) | 延迟分布对比 | Engine 启动/停止 | CPU 使用率监控 |
| P1.2 fast_clock | `test_fast_clock.cpp` (新增) | 延迟对比 | 长时间漂移测试 | 与系统时钟偏差 < 2ms |
| P1.3 object_pool | `test_object_pool.cpp` (新增) | 分配延迟对比 | MPSC 压力测试 | ASAN 无泄漏 |
| P1.4 topic_queue_index | `test_topic_queue_index.cpp` (新增) | `topic_queue_bench.cpp` | 注册/注销一致性 | 并发 stress test |
| P1.5 QuoteTick 对齐 | `test_option_dispatch.cpp` (现有) | — | CTP 模拟回测 | `static_assert` 布局 |
| P2.1 RCU 订阅表 | `test_rcu_snapshot.cpp` (新增) | — | 注册/并发读 | TSAN 验证 |
| P2.2 TLS buffer | `test_message.cpp` (现有) | `serialization_bench.cpp` | 多线程隔离 | 线程安全测试 |
| P2.3 CTP 批量分发 | `test_option_dispatch.cpp` (现有) | `ctp_dispatch_bench.cpp` | 模拟行情压力 | 吞吐量验证 |
| P2.4 send_event_flat | `test_flat_message.cpp` | `e2e_latency_bench.cpp` | C++ module 互操作 | 与 msgpack 数据一致性 |
| P3.1 CPU 亲和性 | `test_thread_affinity.cpp` (新增) | — | Engine 启动 | 平台兼容性 |
| P3.2 基准测试套件 | — | 4 个 benchmark | — | Release 模式验证 |

---

## 实施顺序与工期估算

| 阶段 | 任务 | 工期 | 前置依赖 | 预期收益 |
|------|------|------|----------|----------|
| **Phase 1** | P0.1 flat_serializer.h | 1 天 | 无 | 使现有测试通过 |
| | P0.2 SHM bridge raw | 1 天 | P0.1 | SHM 路径消除 msgpack |
| | P0.3 _enqueue 优化 | 1 天 | P1.1, P1.2, P1.3 | 热路径 3-5x |
| **Phase 2** | P1.1 adaptive_spin | 0.5 天 | 无 | 唤醒延迟 30-300x |
| | P1.2 fast_clock | 0.5 天 | 无 | 时间戳 8x |
| | P1.3 object_pool | 1 天 | 无 | 消除 QueueItem 分配 |
| | P1.4 topic_queue_index | 0.5 天 | 无 | 查找 8x |
| | P1.5 QuoteTick 对齐 | 0.5 天 | 无 | 缓存命中率提升 |
| **Phase 3** | P2.1 RCU 订阅表 | 1 天 | P1.4 | 读路径无锁化 |
| | P2.2 TLS buffer | 0.5 天 | 无 | 序列化零分配 |
| | P2.3 CTP 批量分发 | 0.5 天 | P0.1 | 吞吐量 64x |
| | P2.4 send_event_flat | 0.5 天 | P0.1 | C++ 模块间零序列化 |
| **Phase 4** | P3.1 CPU 亲和性 | 0.5 天 | 无 | 可选 |
| | P3.2 基准测试套件 | 1 天 | 全部 | 量化验证 |

**总计工期：** 约 10-12 个工作日（单人全职），分 4 个阶段逐步实施。

---

## 风险与缓解措施

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| FlatMessage 与 Python 数据不一致 | 中 | 高 | 所有 flat path 必须通过 round-trip 单元测试；Python 路径完全隔离 |
| RDTSC 时钟漂移 | 低 | 中 | 每 1ms 校准；漂移 > 1ms 时自动回退到系统时钟 |
| 自适应轮询导致 CPU 100% | 中 | 中 | 配置化阈值；默认使用 CV；高负载场景手动启用 spin |
| RCU 内存序错误 | 低 | 高 | TSAN 全面验证；stress test 10M+ 操作 |
| ObjectPool 内存泄漏 | 低 | 高 | ASAN/Valgrind 验证；析构时 drain 所有对象 |
| Windows 平台兼容性 | 中 | 中 | 所有代码在 MSVC 和 GCC 双编译器验证；`_mm_pause()` 使用条件编译 |
| 优化叠加导致意外交互 | 中 | 高 | 每阶段独立验证；编译宏隔离；基线测试对比 |

---

## 关键文件路径汇总

### 新建文件
- `src/tyche/cpp/flat_serializer.h`
- `src/tyche/cpp/engine/adaptive_spin.h`
- `src/tyche/cpp/engine/fast_clock.h`
- `src/tyche/cpp/engine/object_pool.h`
- `src/tyche/cpp/engine/topic_queue_index.h`
- `src/tyche/cpp/engine/thread_affinity.h`
- `tests/perf/flat_message_bench.cpp`
- `tests/perf/shm_bridge_bench.cpp`
- `tests/perf/e2e_latency_bench.cpp`
- `tests/perf/alloc_bench.cpp`
- `tests/perf/ctp_dispatch_bench.cpp`
- `tests/cpp/test_adaptive_spin.cpp`
- `tests/cpp/test_fast_clock.cpp`
- `tests/cpp/test_object_pool.cpp`
- `tests/cpp/test_topic_queue_index.cpp`
- `tests/cpp/test_rcu_snapshot.cpp`
- `tests/cpp/test_thread_affinity.cpp`

### 修改文件
- `src/tyche/cpp/engine/engine.h` — 新增 `inject_event_raw()`、`EngineConfig`、RCU 字段、TopicQueueIndex
- `src/tyche/cpp/engine/engine.cpp` — `_enqueue_from_xsub()`、`_event_egress_worker()`、`register_module()`、`_now()`
- `src/tyche/cpp/engine/shared_memory_bridge.cpp` — `_forward_to_zmq()` 使用 raw path
- `src/tyche/cpp/engine/sharded_topic_map.h` / `.cpp` — 新增 `get_raw()` 接口
- `src/tyche/cpp/engine/topic_queue.h` / `.cpp` — 新增 `put_ptr()` / `get_ptr()` 接口
- `src/tyche/cpp/message.h` / `.cpp` — 新增 `serialize_tls()`、`serialize_into()`
- `src/tyche/cpp/module.h` / `.cpp` — 新增 `send_event_flat()`
- `src/modules/ctp_gateway_cpp/src/quote_tick.h` — 缓存行对齐
- `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp` — `option_dispatch_loop()` 批量分发
- `src/tyche/cpp/CMakeLists.txt` — 新增编译宏选项和 benchmark target
- `tests/cpp/CMakeLists.txt` — 新增测试文件和 benchmark target

---

## 与原始计划文档的差异说明

本计划基于 `docs/plan/engine_latency_optimization_plan_v1.md` 进行细化，主要调整如下：

1. **实施策略调整**：根据用户选择，采用保守逐步实施（P0→P1→P2→P3），而非一次性全量实施。
2. **兼容性策略调整**：增加编译宏 + 配置开关控制，每项优化可独立启用/禁用，默认关闭。
3. **平台适配**：所有平台相关代码（RDTSC、CPU亲和性、`_mm_pause()`）使用条件编译，支持 Windows MSVC 和 Linux GCC/Clang。
4. **任务细化**：将原始计划中的大任务拆分为更小、可 review 的子任务（每项 < 300 LOC）。
5. **验证增强**：为每项任务明确指定单元测试、基准测试和集成测试方案。
6. **已存在基础设施复用**：明确标注 FlatMessage、StringIntern、ShardedTopicQueueMap、Frame、RingBuffer、SharedMemoryQueue 等已存在组件，避免重复建设。
