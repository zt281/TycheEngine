# TycheEngine 模块间消息传递系统延迟优化计划

## 概述

本计划基于 MTS v3 高频交易系统架构参考，针对 TycheEngine C++ 引擎（`src/tyche/cpp/engine/`）的模块间消息传递路径进行系统级延迟优化。目标是将端到端消息延迟从当前的微秒级降低到亚微秒级，同时保持与 Python 端的协议兼容性和系统可靠性。

## 当前架构分析

### 消息传递热路径

```
CTP行情回调 → RingBuffer<QuoteTick> → option_dispatch_loop()
  → serialize(Message) → ZMQ PUB socket (tcp://)
  → Engine XSUB → _enqueue_from_xsub() → TopicQueue(RingBuffer)
  → event_egress_worker() → deserialize() → ZMQ XPUB → Module SUB
```

### 当前性能基线（预估，基于 serialization_bench.cpp 设计）

| 操作 | 预估延迟 | 瓶颈分析 |
|------|----------|----------|
| msgpack serialize() | ~800-1200 ns | std::any type dispatch + 堆分配 |
| msgpack deserialize() | ~1000-1500 ns | msgpack::unpack + 多次字符串构造 |
| ZMQ tcp:// 发送+接收 | ~15-30 μs | TCP/IP 栈开销 + 内核态切换 |
| TopicQueue 入队 | ~50-100 ns | CAS + Frame 构造 |
| condition_variable 唤醒 | ~2-5 μs | 内核态唤醒开销 |
| 端到端全链路 | ~25-50 μs | 由 ZMQ tcp:// 主导 |

### 参考基准：MTS v3 性能指标

| 操作 | MTS v3 延迟 | 实现方式 |
|------|-------------|----------|
| 行情到策略 | < 1 μs | 共享内存 + 轮询（零拷贝） |
| 事件分发 | < 500 ns | moodycamel::ConcurrentQueue（无锁） |
| 序列化 | 0 ns | flat struct memcpy（无序列化） |

---

## Task 1: 零拷贝序列化路径（FastPath）

### 问题

当前 `serialize()` 函数存在以下开销：
1. `msgpack::sbuffer` 预分配 512B，仍可能触发重分配
2. `pack_any()` 使用 12 次 `typeid()` 比较链进行类型分派
3. 返回 `std::vector<uint8_t>` 触发堆分配 + memcpy
4. `std::any` 的 RTTI 开销和小对象堆分配

### 解决方案

引入 **FlatMessage** 二进制格式，用于 C++ 模块间的同进程/本机通信：

```cpp
// src/tyche/cpp/flat_message.h
#pragma pack(push, 1)
struct alignas(64) FlatMessageHeader {
    uint8_t  msg_type;          // MessageType enum value
    uint8_t  durability;        // DurabilityLevel enum value
    uint16_t sender_len;        // sender 字符串长度
    uint16_t event_len;         // event 字符串长度
    uint16_t payload_len;       // payload 区域总长度
    uint32_t total_size;        // 整个消息字节数（含 header）
    double   timestamp;         // 高精度时间戳
    // 后续数据区：[sender][event][payload_bytes]
};
#pragma pack(pop)
static_assert(sizeof(FlatMessageHeader) == 24, "FlatMessageHeader size mismatch");
```

**CTP 行情专用快速路径**：

```cpp
// 固定布局的行情消息（参考 MTS v3 的 MarketData struct）
#pragma pack(push, 1)
struct alignas(64) FlatQuoteTick {
    char     symbol[16];    // 合约代码（固定长度，零填充）
    double   bid;
    double   ask;
    double   last;
    int64_t  volume;
    double   timestamp;     // exchange timestamp
    double   local_ts;      // 本地接收时间戳
    uint32_t tick_count;    // 序列号
    uint8_t  flags;         // bit0: is_option, bit1: is_stale
    uint8_t  _pad[3];
};
#pragma pack(pop)
static_assert(sizeof(FlatQuoteTick) == 72, "FlatQuoteTick must be 72 bytes");
```

### 性能目标

| 操作 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| serialize (flat) | ~1000 ns | ~5-10 ns (memcpy) | 100-200x |
| deserialize (flat) | ~1200 ns | ~0 ns (零拷贝指针 cast) | ∞ |
| 堆分配次数 | 3-5 per message | 0 | 完全消除 |

### 实现要点

- FlatMessage 格式仅用于 C++ 模块间通信（ctp_gateway_cpp ↔ engine ↔ greeks_engine_cpp）
- 跨语言通信（C++ ↔ Python）仍使用 msgpack 保持兼容性
- 在 `TycheModule::send_event()` 中增加 `send_event_flat()` 快速路径
- 通过编译期 `constexpr` 标志选择序列化策略

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/tyche/cpp/flat_message.h` | **新建** - FlatMessage 和 FlatQuoteTick 定义 |
| `src/tyche/cpp/flat_serializer.h` | **新建** - 零拷贝序列化/反序列化 inline 函数 |
| `src/tyche/cpp/module.h` | 增加 `send_event_flat()` 方法 |
| `src/tyche/cpp/module.cpp` | 实现 flat path 发送逻辑 |
| `tests/perf/flat_message_bench.cpp` | **新建** - FlatMessage vs msgpack 对比基准 |

---

## Task 2: ZMQ 传输层优化

### 问题

当前所有 ZMQ socket 通过 `Endpoint::to_string()` 硬编码为 `tcp://` 传输：

```cpp
// src/tyche/cpp/types.h:165-167
std::string to_string() const {
    return "tcp://" + host + ":" + std::to_string(port);
}
```

TCP 传输涉及：
- 内核态 TCP/IP 协议栈处理（~5-15 μs）
- Nagle 算法延迟（ZMQ 默认禁用，但仍有系统缓冲）
- 两次内核态↔用户态切换（send + recv）

### 解决方案

#### 2.1 本机通信：`inproc://` + 共享内存双通道

对同进程模块间通信（Engine 内部线程），使用 `inproc://`（零拷贝，零开销）：

```cpp
// Engine 内部线程间通信（event_proxy → event_egress）
// 当前实现已使用 RingBuffer，无需 ZMQ — 保持现状

// 同机不同进程模块间通信：ipc:// (Unix) 或 共享内存
struct Endpoint {
    std::string host;
    int port = 0;
    enum Transport { TCP, IPC, INPROC, SHM } transport = TCP;

    std::string to_string() const {
        switch (transport) {
            case IPC:    return "ipc:///tmp/tyche_" + std::to_string(port);
            case INPROC: return "inproc://tyche_" + std::to_string(port);
            case SHM:    return "";  // 共享内存不使用 ZMQ
            default:     return "tcp://" + host + ":" + std::to_string(port);
        }
    }
};
```

#### 2.2 Windows 平台：命名管道替代 tcp://

Windows 不支持 ZMQ `ipc://`，但支持命名管道模式下的 ZMQ transport：

```cpp
#ifdef _WIN32
    // Windows: 使用 tcp://127.0.0.1 但设置 TCP_NODELAY + 小缓冲区
    socket.set(zmq::sockopt::tcp_keepalive, 1);
    // 或者使用 SharedMemoryQueue 替代 ZMQ（见 Task 2.3）
#else
    // Linux: ipc:// 比 tcp://127.0.0.1 快 2-3x
    socket.bind("ipc:///tmp/tyche_event_pub");
#endif
```

#### 2.3 超低延迟路径：共享内存直通

对 ctp_gateway_cpp → engine 的行情热路径，绕过 ZMQ 使用 SharedMemoryQueue：

```
CTP回调 → FlatQuoteTick → SharedMemoryQueue::write()  [~50ns]
Engine SharedMemoryBridge → _worker_loop() → inject_event()  [~100ns]
```

这与 MTS v3 的 `BlockSharedQueue` 设计完全对齐：
- SPSC 无锁环形缓冲区
- sequence number 同步
- 轮询模式（非阻塞，避免 condition_variable 开销）

### 性能目标

| 传输方式 | 延迟 (单次消息) | 适用场景 |
|----------|-----------------|----------|
| tcp://127.0.0.1 | 15-30 μs | 跨机器、远程模块 |
| ipc:// (Linux) | 5-8 μs | 同机不同进程 |
| SharedMemoryQueue | 50-200 ns | 同机 C++ 模块（热路径） |
| inproc:// | 1-3 μs | 同进程不同线程 |

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/tyche/cpp/types.h` | Endpoint 增加 transport 枚举 |
| `src/tyche/cpp/engine/engine.cpp` | SharedMemoryBridge 轮询频率优化 |
| `src/tyche/cpp/engine/shared_memory_bridge.cpp` | 增加 busy-poll 模式 |
| `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp` | 增加 SHM 直通发送路径 |
| `tests/perf/transport_bench.cpp` | **新建** - 传输层延迟对比基准 |

---

## Task 3: 消息队列热路径优化

### 问题

`_enqueue_from_xsub()` 是事件代理的核心热路径，当前实现存在：

1. **vector 分配**：`std::vector<Frame> fframes` 每次入队构造新 vector
2. **字符串构造**：`std::string topic(frames[0].begin(), frames[0].end())` 每帧构造临时 string
3. **shared_ptr 引用计数**：`get_or_create()` 返回 `shared_ptr<TopicQueue>` 引起原子引用计数增减
4. **时间戳获取**：`_now()` 调用 `system_clock::now()` + duration_cast（系统调用开销）

### 解决方案

#### 3.1 预分配 Frame 数组

使用固定大小的栈上 Frame 数组代替 `vector<Frame>`：

```cpp
// 优化后的入队路径
void TycheEngine::_enqueue_from_xsub(
    const std::vector<std::vector<uint8_t>>& frames) {
    if (frames.size() < 2) return;

    // 栈上 topic string_view（避免 heap 分配）
    std::string_view topic_sv(
        reinterpret_cast<const char*>(frames[0].data()), frames[0].size());

    // 使用 InternId 快速查找队列（避免字符串哈希）
    InternId topic_id = _intern.lookup(topic_sv);
    if (topic_id == INVALID_INTERN_ID) {
        // 冷路径：未注册的 topic，走完整 string 构造
        std::string topic(topic_sv);
        topic_id = _intern.intern(topic);
    }

    // 直接获取 TopicQueue 裸指针（避免 shared_ptr 引用计数）
    TopicQueue* q = _topic_queues.get_raw(topic_id);
    if (!q) return;

    // 使用 FixedFrameArray 避免 vector 堆分配
    static constexpr size_t MAX_FRAMES = 4;
    Frame fixed_frames[MAX_FRAMES];
    size_t n = std::min(frames.size(), MAX_FRAMES);
    for (size_t i = 0; i < n; ++i) {
        fixed_frames[i] = Frame(frames[i].data(), frames[i].size());
    }
    // ...
}
```

#### 3.2 基于 InternId 的直接数组索引

替代 ShardedTopicQueueMap 的字符串哈希查找：

```cpp
// 新增：基于 InternId 的直接索引表（O(1) 查找，无锁）
class TopicQueueIndex {
    std::vector<TopicQueue*> _queues;  // index = InternId
public:
    TopicQueue* get(InternId id) const noexcept {
        return (id < _queues.size()) ? _queues[id] : nullptr;
    }
    void set(InternId id, TopicQueue* q) {
        if (id >= _queues.size()) _queues.resize(id + 1, nullptr);
        _queues[id] = q;
    }
};
```

#### 3.3 时间戳缓存

使用 RDTSC + 周期性校准，避免频繁系统调用：

```cpp
// 参考 MTS v3 的 SyncTime 机制
class FastClock {
    static inline std::atomic<double> _cached_time{0.0};
    static inline std::atomic<uint64_t> _tsc_base{0};
    static inline double _tsc_to_ns{1.0};
public:
    static double now() noexcept {
        // 快速路径：使用缓存的时间戳（由后台线程每 1ms 更新）
        return _cached_time.load(std::memory_order_relaxed);
    }
    static double now_precise() noexcept {
        // 精确路径：使用 RDTSC 差值推算
        // ...
    }
};
```

### 性能目标

| 操作 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| _enqueue_from_xsub | ~150 ns | ~30-50 ns | 3-5x |
| topic 查找 | ~40 ns (hash+spinlock) | ~5 ns (array index) | 8x |
| 时间戳获取 | ~25 ns (syscall) | ~3 ns (cached) | 8x |
| Frame vector 构造 | ~30 ns (heap alloc) | ~0 ns (stack) | ∞ |

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/tyche/cpp/engine/engine.cpp` | `_enqueue_from_xsub` 优化实现 |
| `src/tyche/cpp/engine/topic_queue_index.h` | **新建** - InternId 直接索引表 |
| `src/tyche/cpp/engine/fast_clock.h` | **新建** - 快速时间戳 |
| `src/tyche/cpp/engine/sharded_topic_map.h` | 增加 `get_raw()` 裸指针接口 |
| `src/tyche/cpp/string_intern.h` | 增加 `lookup(string_view)` 无分配版本 |

---

## Task 4: 线程同步开销优化

### 问题

当前线程模型的主要同步开销：

1. **egress_wakeup_cv**：`event_egress_worker` 使用 `condition_variable::wait_for(1s)` 等待事件，唤醒延迟 ~2-5 μs
2. **shared_mutex (modules_lock)**：事件分发时读取 subscriber 列表需要 shared_lock
3. **reg_in_cv**：注册工作线程使用 condition_variable 等待
4. **job_lock**：Job 路由器使用 `std::mutex` 保护 tracking 状态

### 解决方案

#### 4.1 Egress Worker：轮询 + 自适应休眠

参考 MTS v3 的 HardWorker 轮询模式：

```cpp
void TycheEngine::_event_egress_worker() {
    int idle_count = 0;
    constexpr int SPIN_THRESHOLD = 1000;      // 自旋 1000 次
    constexpr int YIELD_THRESHOLD = 10000;    // yield 10000 次
    constexpr int SLEEP_US = 10;              // 最终休眠 10μs

    while (_running.load(std::memory_order_relaxed)) {
        bool had_work = false;
        auto queues = _topic_queues.snapshot();
        for (auto& [topic, q] : queues) {
            auto item = q->get();
            if (item.has_value()) {
                had_work = true;
                idle_count = 0;
                // 处理 item...
            }
        }

        if (!had_work) {
            ++idle_count;
            if (idle_count < SPIN_THRESHOLD) {
                _mm_pause();  // 自旋等待
            } else if (idle_count < YIELD_THRESHOLD) {
                std::this_thread::yield();
            } else {
                std::this_thread::sleep_for(std::chrono::microseconds(SLEEP_US));
            }
        }
    }
}
```

#### 4.2 模块订阅表：Read-Copy-Update (RCU)

替代 `shared_mutex`，使用 RCU 模式实现无锁读路径：

```cpp
// 订阅表快照：注册时原子替换，读取时无锁
struct SubscriptionSnapshot {
    std::unordered_map<InternId, std::vector<std::string>> topic_subscribers;
    std::unordered_map<InternId, std::vector<std::string>> topic_producers;
    std::unordered_map<InternId, std::vector<std::string>> job_handlers;
};

// Engine 持有 atomic<shared_ptr>：
std::atomic<std::shared_ptr<SubscriptionSnapshot>> _subscription_snapshot;

// 热路径读取（无锁）：
auto snap = _subscription_snapshot.load(std::memory_order_acquire);
auto it = snap->topic_subscribers.find(topic_id);
// ...

// 注册/注销时（冷路径）：
auto new_snap = std::make_shared<SubscriptionSnapshot>(*old_snap);
// 修改 new_snap...
_subscription_snapshot.store(new_snap, std::memory_order_release);
```

#### 4.3 CPU 亲和性绑定

参考 MTS v3 的 HardWorker 核绑定策略：

```cpp
// 关键热路径线程绑核
void TycheEngine::start_nonblocking() {
    // event_proxy_worker 绑定到专用 CPU 核
    auto proxy_thread = std::thread(&TycheEngine::_event_proxy_worker, this);
    set_thread_affinity(proxy_thread, config.event_proxy_core);

    // event_egress_worker 绑定到相邻核（利用 L2 缓存共享）
    auto egress_thread = std::thread(&TycheEngine::_event_egress_worker, this);
    set_thread_affinity(egress_thread, config.event_egress_core);
}
```

### 性能目标

| 同步机制 | 优化前 | 优化后 | 提升 |
|----------|--------|--------|------|
| egress 唤醒延迟 | ~3000 ns (CV) | ~10-100 ns (spin) | 30-300x |
| 订阅表查找 | ~50 ns (shared_lock) | ~5 ns (atomic load) | 10x |
| 上下文切换 | ~5000 ns | 0 ns (busy-poll) | ∞ |

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/tyche/cpp/engine/engine.cpp` | egress worker 改为自适应轮询 |
| `src/tyche/cpp/engine/engine.h` | 增加 SubscriptionSnapshot + RCU 字段 |
| `src/tyche/cpp/engine/thread_affinity.h` | **新建** - 跨平台 CPU 亲和性工具 |
| `src/tyche/cpp/engine/adaptive_spin.h` | **新建** - 自适应自旋等待器 |

---

## Task 5: 内存分配热路径消除

### 问题

热路径上的堆分配点：

| 位置 | 分配原因 | 频率 |
|------|----------|------|
| `serialize()` 返回 `vector<uint8_t>` | sbuffer → vector 复制 | 每条消息 |
| `deserialize()` 中 `std::string` 构造 | payload key/value 字符串 | 每个字段 |
| `std::any` 存储 | 小对象堆分配（实现相关） | 每个 payload 值 |
| `QueueItem::frames` vector | vector 元数据 | 每次入队 |
| `to_bytes()` 返回 vector | ZMQ frame 转 vector | 每帧 |
| `_enqueue_from_xsub` bframes vector | frames 转换中间 vector | 每条消息 |

### 解决方案

#### 5.1 Arena 分配器用于消息序列化

```cpp
// 线程局部 arena 分配器（每条消息复用，零系统调用）
class MessageArena {
    static constexpr size_t ARENA_SIZE = 4096;
    alignas(64) uint8_t _buffer[ARENA_SIZE];
    size_t _offset = 0;
public:
    void reset() noexcept { _offset = 0; }

    uint8_t* allocate(size_t n) noexcept {
        n = (n + 7) & ~7;  // 8 字节对齐
        if (_offset + n > ARENA_SIZE) return nullptr;  // 回退到堆
        uint8_t* p = _buffer + _offset;
        _offset += n;
        return p;
    }

    // 返回视图而非 vector
    struct BufferView {
        const uint8_t* data;
        size_t size;
    };
};

// 改进的 serialize 接口
BufferView serialize_to_arena(const Message& msg, MessageArena& arena);
```

#### 5.2 对象池用于 QueueItem

```cpp
// 固定大小对象池（无锁 MPSC free-list）
template<typename T, size_t PoolSize = 65536>
class ObjectPool {
    struct alignas(CACHE_LINE_SIZE) Slot {
        std::atomic<Slot*> next;
        alignas(alignof(T)) uint8_t storage[sizeof(T)];
    };
    std::atomic<Slot*> _free_list;
    std::vector<Slot> _slots;
public:
    T* acquire() {
        Slot* s = _free_list.load(std::memory_order_acquire);
        while (s && !_free_list.compare_exchange_weak(
            s, s->next.load(std::memory_order_relaxed),
            std::memory_order_release, std::memory_order_relaxed)) {}
        if (!s) return nullptr;
        return new (s->storage) T();
    }
    void release(T* obj) {
        obj->~T();
        auto* s = reinterpret_cast<Slot*>(
            reinterpret_cast<uint8_t*>(obj) - offsetof(Slot, storage));
        Slot* head = _free_list.load(std::memory_order_relaxed);
        do { s->next.store(head, std::memory_order_relaxed); }
        while (!_free_list.compare_exchange_weak(
            head, s, std::memory_order_release, std::memory_order_relaxed));
    }
};
```

#### 5.3 消除 serialize() 返回值分配

```cpp
// 当前：std::vector<uint8_t> serialize(const Message& msg);
// 改进：写入调用者提供的缓冲区
size_t serialize_into(const Message& msg, uint8_t* buffer, size_t capacity);

// 或使用线程局部缓冲区
thread_local static msgpack::sbuffer tls_buffer(4096);
const uint8_t* serialize_tls(const Message& msg, size_t& out_size) {
    tls_buffer.clear();
    msgpack::packer<msgpack::sbuffer> pk(&tls_buffer);
    // ... pack ...
    out_size = tls_buffer.size();
    return reinterpret_cast<const uint8_t*>(tls_buffer.data());
}
```

### 性能目标

| 操作 | 优化前 | 优化后 | 说明 |
|------|--------|--------|------|
| serialize 分配 | ~60 ns (malloc+copy) | 0 ns (TLS buffer) | 消除堆分配 |
| QueueItem 构造 | ~80 ns (vector alloc) | ~10 ns (pool acquire) | 对象池复用 |
| 每条消息总堆操作 | 5-8 次 | 0-1 次 | 热路径无分配 |

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/tyche/cpp/engine/message_arena.h` | **新建** - 线程局部 arena |
| `src/tyche/cpp/engine/object_pool.h` | **新建** - 无锁对象池 |
| `src/tyche/cpp/message.h` | 增加 `serialize_into()` 和 `serialize_tls()` 接口 |
| `src/tyche/cpp/message.cpp` | 实现零分配序列化路径 |
| `src/tyche/cpp/engine/topic_queue.h` | QueueItem 使用对象池 |

---

## Task 6: CTP Gateway 专用优化

### 问题

ctp_gateway_cpp 模块的行情处理路径存在以下开销：

1. **QuoteTick → Payload 转换**：`tick_to_payload()` 构造多个 `std::string` 键和 `std::any` 值
2. **RingBuffer<QuoteTick>** 的 QuoteTick 结构未对齐到缓存行
3. **option_dispatch_loop** 使用 `try_push` + `sleep(1ms)` 轮询，延迟高
4. **行情回调线程**到分发线程的跨线程通信缺乏内存屏障优化

### 解决方案

#### 6.1 QuoteTick 缓存行对齐

```cpp
// 当前 QuoteTick 可能跨缓存行边界，导致 false sharing
// 参考 MTS v3 的 MarketData struct 设计
struct alignas(64) QuoteTick {
    // Hot fields (most frequently read) — first cache line
    char     instrument_id[32];     // 合约代码
    double   last_price;
    double   bid_price1;
    double   ask_price1;
    int32_t  bid_volume1;
    int32_t  ask_volume1;
    int64_t  volume;
    // --- 64 bytes ---

    // Cold fields — second cache line
    double   open_interest;
    double   turnover;
    double   upper_limit;
    double   lower_limit;
    char     update_time[16];
    int32_t  update_millisec;
    uint32_t sequence;              // 用于乱序检测
    uint8_t  flags;                 // is_option | is_valid | is_stale
    uint8_t  _pad[7];
    // --- 128 bytes total ---
};
static_assert(sizeof(QuoteTick) == 128, "QuoteTick must be 128 bytes (2 cache lines)");
```

#### 6.2 零序列化行情广播

对 C++ greeks_engine 模块，直接通过 SharedMemoryQueue 传递 FlatQuoteTick：

```cpp
void CtpGateway::on_quote_received_fast(const QuoteTick& tick) {
    if (is_option(tick)) {
        // 期权行情：写入 SharedMemoryQueue（引擎自动转发给 greeks_engine）
        shm_queue_->write(
            reinterpret_cast<const uint8_t*>(&tick), sizeof(QuoteTick));
    } else {
        // 期货行情：通过 RingBuffer 送入本地 event_proxy
        // 直接 memcpy FlatQuoteTick 到 ZMQ frame（无序列化）
        zmq::message_t msg(&tick, sizeof(QuoteTick));
        pub_socket_.send(topic_frame_, zmq::send_flags::sndmore);
        pub_socket_.send(std::move(msg), zmq::send_flags::none);
    }
}
```

#### 6.3 option_dispatch_loop 低延迟改造

参考 MTS v3 的 HardWorker 轮询模型：

```cpp
void CtpGateway::option_dispatch_loop() {
    int idle_spins = 0;
    while (ctp_running_.load(std::memory_order_relaxed)) {
        auto tick = option_ring_buffer_.pop();
        if (tick.has_value()) {
            idle_spins = 0;
            // 批量弹出优化：连续弹出最多 64 个 tick 后再发送
            QuoteTick batch[64];
            batch[0] = std::move(*tick);
            size_t batch_size = 1;
            while (batch_size < 64) {
                auto next = option_ring_buffer_.pop();
                if (!next.has_value()) break;
                batch[batch_size++] = std::move(*next);
            }
            // 批量发送
            for (size_t i = 0; i < batch_size; ++i) {
                send_event_flat("send_compute_greeks", batch[i]);
            }
        } else {
            // 自适应等待（参考 Task 4 的三级退避）
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

### 性能目标

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| CTP回调→Engine 延迟 | ~30 μs (ZMQ tcp) | ~200 ns (SHM) | 150x |
| QuoteTick 序列化 | ~1000 ns | 0 ns (零拷贝) | ∞ |
| option_dispatch 唤醒 | ~1 ms (sleep) | ~100 ns (spin) | 10000x |
| 批量发送效率 | 1 msg/loop | 最多 64 msg/loop | 64x 吞吐 |

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/modules/ctp_gateway_cpp/src/quote_tick.h` | QuoteTick 缓存行对齐重构 |
| `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp` | 增加 SHM 直通路径 + 批量分发 |
| `src/modules/ctp_gateway_cpp/src/ctp_gateway.h` | 增加 SHM queue 成员 |
| `src/modules/ctp_gateway_cpp/src/md_spi.cpp` | 回调路径优化 |

---

## Task 7: 性能基准测试套件

### 新增基准测试

| 测试文件 | 测量内容 |
|----------|----------|
| `tests/perf/flat_message_bench.cpp` | FlatMessage vs msgpack serialize/deserialize 对比 |
| `tests/perf/transport_bench.cpp` | tcp vs ipc vs SharedMemoryQueue 端到端延迟 |
| `tests/perf/e2e_latency_bench.cpp` | 完整链路：CTP模拟→Engine→Module 端到端延迟分布 |
| `tests/perf/alloc_bench.cpp` | 热路径内存分配统计（tcmalloc/jemalloc 对比） |

### 基准测试框架

```cpp
// 延迟统计收集器
struct LatencyStats {
    uint64_t count = 0;
    double min_ns = DBL_MAX;
    double max_ns = 0;
    double sum_ns = 0;
    std::vector<double> samples;  // 用于百分位计算

    void record(double ns) {
        ++count;
        min_ns = std::min(min_ns, ns);
        max_ns = std::max(max_ns, ns);
        sum_ns += ns;
        samples.push_back(ns);
    }

    double p50() const;
    double p99() const;
    double p999() const;
    double avg() const { return sum_ns / count; }
};
```

### CMake 集成

```cmake
# tests/perf/CMakeLists.txt
add_executable(flat_message_bench flat_message_bench.cpp)
add_executable(transport_bench transport_bench.cpp)
add_executable(e2e_latency_bench e2e_latency_bench.cpp)
add_executable(alloc_bench alloc_bench.cpp)
```

---

## 优化优先级与实施顺序

| 优先级 | Task | 预期收益 | 风险 | 工期估算 |
|--------|------|----------|------|----------|
| P0 | Task 2.3 (SHM直通) | 端到端延迟降低 100x+ | 低（已有 SharedMemoryQueue 基础设施） | 2-3 天 |
| P0 | Task 1 (FlatMessage) | 序列化延迟降低 100x+ | 中（需维护双格式兼容） | 3-4 天 |
| P1 | Task 4.1 (轮询替代CV) | 唤醒延迟降低 30-300x | 低（CPU 使用率增加） | 1 天 |
| P1 | Task 6.1 (QuoteTick 对齐) | 缓存命中率提升 | 低（纯内存布局优化） | 0.5 天 |
| P1 | Task 3.2 (InternId 索引) | 查找延迟降低 8x | 低（增量优化） | 1 天 |
| P2 | Task 5 (内存分配消除) | 每消息减少 5-8 次 malloc | 中（API 变更影响面大） | 3-4 天 |
| P2 | Task 4.2 (RCU 订阅表) | 读路径无锁化 | 中（需验证内存序正确性） | 2 天 |
| P2 | Task 6.3 (批量分发) | 吞吐量提升 64x | 低 | 1 天 |
| P3 | Task 4.3 (CPU 亲和性) | 减少缓存失效 | 低（配置化，可选） | 0.5 天 |
| P3 | Task 7 (基准测试) | 量化验证优化效果 | 无 | 2 天 |

---

## 兼容性保证

### 协议兼容性

1. **Python ↔ C++ 通信**：仍使用 msgpack 序列化 + ZMQ tcp:// 传输，不受影响
2. **C++ ↔ C++ 本机通信**：增加 FlatMessage 快速路径作为可选 opt-in
3. **配置驱动**：通过 JSON 配置文件选择传输模式（tcp/ipc/shm），默认保持 tcp 向后兼容

### 功能正确性

1. FlatMessage 必须通过 round-trip 单元测试验证数据完整性
2. SharedMemoryQueue 必须通过 TSAN (Thread Sanitizer) 验证无数据竞争
3. RCU 订阅表必须通过并发 stress test 验证一致性
4. 所有优化必须在现有 `tests/cpp/` 测试全部通过的前提下合入

### 回退机制

- 每项优化通过编译宏 (`TYCHE_OPT_FLAT_MSG`, `TYCHE_OPT_SHM_DIRECT`, etc.) 控制
- 可通过配置文件在运行时回退到原始路径
- 性能劣化超过 5% 的优化不合入

---

## 总结：预期端到端延迟

| 场景 | 优化前 | 优化后 (P0+P1) | 优化后 (全部) |
|------|--------|----------------|---------------|
| CTP行情→Engine (同机) | 25-50 μs | 200-500 ns | 50-200 ns |
| Engine→Module (同机 C++) | 20-40 μs | 100-300 ns | 30-100 ns |
| Engine→Module (Python) | 25-50 μs | 20-40 μs (不变) | 15-30 μs (ipc) |
| 完整链路 (C++ 全路径) | 50-100 μs | 500 ns - 1 μs | 100-500 ns |

与 MTS v3 参考目标对齐：
- 行情到策略：< 1 μs (目标) → 优化后 100-500 ns (达成)
- 事件分发：< 500 ns (目标) → 优化后 30-100 ns (超越)
