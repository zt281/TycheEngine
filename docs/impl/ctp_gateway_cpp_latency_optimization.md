# CTP Gateway CPP 延迟性能优化方案

> 基于 MTS v3 HFT 系统工程实践，针对 `ctp_gateway_cpp` 模块的延迟性能分析与优化方案。
> 分析日期：2026-06-13
> 相关文件：`src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`、`src/tyche/cpp/module.cpp`、`src/tyche/cpp/message.cpp`

---

## 1. 当前 CTP 网关延迟来源分析

### 1.1 网络延迟（外部不可控）

| 来源 | 延迟量级 | 说明 |
|------|---------|------|
| CTP 前置机 → 交易所 | 10~50ms | 物理网络延迟，不可优化 |
| CTP 行情推送回调 | ~1ms | 交易所撮合后广播，不可优化 |

### 1.2 序列化/反序列化开销（内部可控）

在 `message.cpp` 中，每条行情从 CTP 回调到 ZMQ 发送经历以下序列化：

1. **`md_spi.cpp: depth_to_payload()`**：创建 `std::unordered_map<std::string, std::any>`，涉及大量 `std::string` 构造和 `std::any` 类型擦除
2. **`message.cpp: serialize()`**：将 `Message` 序列化为 msgpack 字节流，遍历 `Payload` 的每个键值对
3. **`message.cpp: deserialize()`**：引擎端接收后反序列化（同样遍历键值对）

**问题**：`std::any` 类型擦除带来虚函数开销和额外内存分配；`std::unordered_map` 在热路径上哈希计算开销较大。

### 1.3 线程同步开销

| 位置 | 同步机制 | 问题 |
|------|---------|------|
| `module.cpp: send_event()` | `std::lock_guard<std::mutex> lock(_impl->pub_lock)` | 每条行情发送都加锁，多线程竞争 |
| `ctp_gateway.cpp: on_quote_received()` | `std::lock_guard<std::mutex> lock(option_queue_mtx_)` | 期权行情入队加锁 |
| `ctp_gateway.cpp: option_dispatch_loop()` | `std::unique_lock + condition_variable` | 20ms 超时轮询，存在唤醒延迟 |
| `module.cpp: request_event()` | `std::lock_guard<std::mutex> lock(_impl->job_lock)` + `_pending_lock` | Job 请求发送和等待响应双重锁 |

### 1.4 内存分配开销

- `depth_to_payload()` 中 `Payload` 和内部 `std::string` 的堆分配
- `serialize()` 中 `msgpack::sbuffer` 和 `std::vector<uint8_t>` 的堆分配
- `send_event()` 中 `zmq::message_t` 的构造（虽然 ZMQ 有零拷贝模式，但当前未使用）

---

## 2. 热点路径（Hot Path）性能分析

### 2.1 `on_quote_received()` — 行情回调分发

```cpp
void CtpGateway::on_quote_received(const tyche::Payload& payload) {
    // 1. 从 Payload 中查找 instrument_id（std::any_cast）
    std::string instrument_id;
    try {
        auto it = payload.find("instrument_id");
        if (it != payload.end()) {
            instrument_id = std::any_cast<std::string>(it->second);
        }
    } catch (...) {}

    // 2. 二分查找判断是否为期权（std::binary_search）
    bool is_option = false;
    if (!instrument_id.empty()) {
        is_option = std::binary_search(
            option_instruments_.begin(), option_instruments_.end(), instrument_id);
    }

    // 3. 分支处理
    if (is_option) {
        // 期权：加锁入队 + notify_one
        std::lock_guard<std::mutex> lock(option_queue_mtx_);
        if (option_queue_.size() < 10000) {
            option_queue_.push(payload);  // Payload 拷贝
        }
        option_queue_cv_.notify_one();
    } else {
        // 期货：send_event（序列化 + ZMQ 发送 + 加锁）
        send_event("quote", payload);
    }
}
```

**热点问题**：
- `std::any_cast<std::string>` 有类型检查开销
- `std::binary_search` 在 `option_instruments_` 上查找，虽然 O(log n)，但字符串比较仍有开销
- 期权分支：`Payload` 拷贝入队（`std::queue<tyche::Payload>` 的 `push` 是拷贝构造）
- 期货分支：`send_event()` 内部包含 `serialize()` + `zmq::socket_t::send()` + `mutex` 锁

### 2.2 `option_dispatch_loop()` — 期权 Job 分发

```cpp
void CtpGateway::option_dispatch_loop() {
    while (ctp_running_.load() || !option_queue_.empty()) {
        tyche::Payload tick;
        {
            std::unique_lock<std::mutex> lock(option_queue_mtx_);
            option_queue_cv_.wait_for(lock, std::chrono::milliseconds(20),
                [this]() { return !option_queue_.empty() || !ctp_running_.load(); });
            if (option_queue_.empty()) {
                if (!ctp_running_.load()) break;
                continue;
            }
            tick = std::move(option_queue_.front());
            option_queue_.pop();
        }

        // 发送 compute_greeks job（阻塞等响应）
        try {
            request_event("compute_greeks", tick, 10.0f);
        } catch (const std::exception& e) {
            // ...
        }
    }
}
```

**热点问题**：
- `wait_for(20ms)` 导致最大 20ms 的调度延迟（即使队列有数据，也可能因超时未精确唤醒）
- `request_event()` 是**同步阻塞**调用：发送 → 等待引擎路由 → 等待 greeks_engine 处理 → 等待响应返回
- 每条期权行情都经历一次完整的 REQ-REP 往返，延迟 = 2×ZMQ传输 + 引擎调度 + greeks_engine 计算

---

## 3. ZeroMQ inproc 延迟评估

### 3.1 当前使用 `tcp://` 而非 `inproc://`

在 `module.cpp` 中：
```cpp
std::string pub_endpoint = "tcp://" + _engine_endpoint.host + ":" +
                           std::to_string(_impl->engine_sub_port);
_impl->pub_socket->connect(pub_endpoint);
```

**问题**：即使是本机通信，也使用 `tcp://` 协议，经过 OS 网络栈（loopback），延迟约 **50~100μs**。

### 3.2 `inproc://` 延迟特性

| 传输方式 | 典型延迟 | 适用场景 |
|---------|---------|---------|
| `tcp://localhost` | 50~100μs | 跨机器、兼容性 |
| `inproc://` | **<<1μs** | 同进程内线程通信 |
| `ipc://` | 10~50μs | 同机器跨进程 |

**关键限制**：`inproc://` 要求所有 socket 共享同一个 `zmq::context_t`，且必须在同一进程内。当前 CTP 网关和 TycheEngine 是**不同进程**，因此无法直接使用 `inproc://`。

### 3.3 结论：`<10μs` 目标是否可达？

| 场景 | 可达性 | 说明 |
|------|--------|------|
| CTP 网关 → 引擎（同机 tcp） | **不可达** | tcp loopback 最低约 50μs，加上序列化后通常 >100μs |
| 引擎内部路由（inproc） | **可达** | 引擎内部线程间可用 inproc，<<1μs |
| 跨进程优化 | **部分可达** | 使用共享内存（SHM）替代 ZMQ tcp，可达 <10μs |

---

## 4. 混合路由策略优化建议

当前策略：
- **期货**：`send_event("quote", payload)` → 广播给所有 greeks_engine
- **期权**：`request_event("compute_greeks", tick, 10.0f)` → 轮询 Job 分发到单个实例

### 4.1 问题分析

| 问题 | 影响 |
|------|------|
| 期权同步阻塞 | `request_event` 阻塞分发线程，吞吐量受限于 greeks_engine 处理速度 |
| 无批量处理 | 每条期权行情单独发 Job，无法摊平序列化和网络开销 |
| 期货广播无过滤 | 所有 greeks_engine 都接收期货行情，即使某些实例不需要 |

### 4.2 优化建议

**建议 1：期权改为异步批量 Job 提交**

将同步 `request_event` 改为异步 `send_event` + 批量聚合：

```cpp
// 新设计：期权行情也推入队列，但由分发线程批量打包发送
struct OptionBatch {
    std::vector<tyche::Payload> ticks;
    std::chrono::steady_clock::time_point deadline;
};

// 每 1ms 或攒满 32 条触发一次批量 compute_greeks job
```

**建议 2：期货广播增加 Topic 细分**

按交易所或品种细分 `quote` topic，让 greeks_engine 只订阅需要的子集：

```cpp
send_event("quote.SHFE.au", payload);  // 而非统一的 "quote"
```

**建议 3：期权 Job 改为无等待异步发送**

如果不需要计算结果回传，直接发事件而非 Job：

```cpp
// 如果 greeks_engine 计算结果不需要返回给网关
send_event("compute_greeks", payload, recipient);  // 点对点发送给特定实例
```

---

## 5. 具体代码级优化措施

### 5.1 减少内存分配：使用对象池和预分配

**优化 `depth_to_payload()`**：使用固定结构体替代 `Payload`

```cpp
// 新增： QuoteTick 结构体（POD，无动态分配）
struct QuoteTick {
    char instrument_id[32];
    char exchange_id[16];
    double last_price;
    int volume;
    double bid_price1;
    int bid_volume1;
    double ask_price1;
    int ask_volume1;
    double upper_limit_price;
    double lower_limit_price;
    double open_price;
    double high_price;
    double low_price;
    double pre_settle_price;
    double open_interest;
    double turnover;
    char update_time[16];
    int update_millisec;
    char trading_day[16];
    bool is_option;  // 预标记，避免运行时查找
};

// MdSpiImpl 中直接填充 QuoteTick，避免 unordered_map + any
```

**优化序列化**：对 `QuoteTick` 使用 flatbuffer 或自定义紧凑格式

```cpp
// 替代 msgpack 的通用序列化，使用固定大小的二进制格式
std::vector<uint8_t> serialize_quote_tick(const QuoteTick& tick) {
    std::vector<uint8_t> buf(sizeof(QuoteTick));
    std::memcpy(buf.data(), &tick, sizeof(QuoteTick));
    return buf;
}
```

### 5.2 优化线程同步：使用无锁队列

**替换 `std::queue + mutex` 为 `boost::lockfree::spsc_queue` 或自旋锁**

```cpp
#include <boost/lockfree/spsc_queue.hpp>

// 单生产者（CTP 回调线程）单消费者（分发线程）场景
boost::lockfree::spsc_queue<tyche::Payload, boost::lockfree::capacity<65536>> option_queue_;

void on_quote_received(const tyche::Payload& payload) {
    if (is_option) {
        // 无锁入队
        while (!option_queue_.push(payload)) {
            // 队列满，丢弃最旧或自旋等待
        }
    }
}
```

### 5.3 优化 ZMQ 发送：批量发送 + 零拷贝

**优化 `send_event()`：支持批量发送**

```cpp
// module.h 中新增批量发送接口
void send_events(const std::string& event,
                 const std::vector<Payload>& payloads);

// 实现：使用 ZMQ 的 multipart 消息批量发送
void TycheModule::send_events(const std::string& event,
                               const std::vector<Payload>& payloads) {
    std::lock_guard<std::mutex> lock(_impl->pub_lock);
    for (size_t i = 0; i < payloads.size(); ++i) {
        auto buffer = serialize(/* ... */);
        zmq::message_t topic(event.data(), event.size());
        zmq::message_t data(buffer.data(), buffer.size());
        auto flags = (i == payloads.size() - 1) ? zmq::send_flags::none
                                               : zmq::send_flags::sndmore;
        _impl->pub_socket->send(topic, zmq::send_flags::sndmore);
        _impl->pub_socket->send(data, flags);
    }
}
```

**使用 ZMQ 零拷贝（zero-copy）**

```cpp
// 使用 zmq::message_t 的 zero-copy 构造
zmq::message_t data(buffer.data(), buffer.size(), 
                    [](void* /*data*/, void* /*hint*/){});
```

### 5.4 优化期权路由：异步 + 批量

**重构 `option_dispatch_loop()` 为批量异步模式**

```cpp
void CtpGateway::option_dispatch_loop() {
    constexpr size_t BATCH_SIZE = 32;
    constexpr auto BATCH_TIMEOUT = std::chrono::milliseconds(1);
    
    std::vector<tyche::Payload> batch;
    batch.reserve(BATCH_SIZE);
    
    while (ctp_running_.load() || !option_queue_.empty()) {
        // 使用 wait_for 但超时缩短到 1ms
        tyche::Payload tick;
        bool got_one = false;
        {
            std::unique_lock<std::mutex> lock(option_queue_mtx_);
            option_queue_cv_.wait_for(lock, BATCH_TIMEOUT,
                [this]() { return !option_queue_.empty() || !ctp_running_.load(); });
            if (!option_queue_.empty()) {
                tick = std::move(option_queue_.front());
                option_queue_.pop();
                got_one = true;
            }
        }
        
        if (got_one) {
            batch.push_back(std::move(tick));
        }
        
        // 批量触发条件：满 32 条，或 1ms 超时且至少有一条
        if (batch.size() >= BATCH_SIZE || 
            (!batch.empty() && !got_one && !ctp_running_.load()) ||
            (!batch.empty() && std::chrono::steady_clock::now() > next_deadline)) {
            
            // 改为异步发送，不等待响应
            send_event("compute_greeks_batch", make_batch_payload(batch));
            batch.clear();
            next_deadline = std::chrono::steady_clock::now() + BATCH_TIMEOUT;
        }
    }
}
```

### 5.5 优化 `request_event()`：减少锁粒度

当前 `request_event()` 使用 `_pending_lock` 保护整个等待过程，可以改为条件变量 + 原子标志：

```cpp
// 使用 std::atomic<bool> + std::mutex 分离状态检查和等待
struct PendingRequest {
    Payload result;
    std::atomic<bool> ready{false};
    std::mutex mtx;
    std::condition_variable cv;
};
```

### 5.6 使用 `ipc://` 替代 `tcp://`（同机场景）

在 `module.cpp` 中检测同机通信：

```cpp
if (_engine_endpoint.host == "127.0.0.1" || _engine_endpoint.host == "localhost") {
    pub_endpoint = "ipc:///tmp/tyche_pub_" + std::to_string(_impl->engine_sub_port);
} else {
    pub_endpoint = "tcp://" + _engine_endpoint.host + ":" + std::to_string(_impl->engine_sub_port);
}
```

---

## 6. 异步处理和批处理策略

### 6.1 期货行情：保持广播，增加批处理窗口

```cpp
// 在 CTP 回调线程中不立即发送，而是推入无锁队列
// 由独立发送线程每 500μs 批量 flush

class QuoteBatcher {
    boost::lockfree::spsc_queue<QuoteTick> incoming_;
    std::vector<QuoteTick> buffer_;
    std::chrono::microseconds flush_interval_{500};
    
public:
    void on_tick(QuoteTick tick) {
        while (!incoming_.push(tick)) {}  // 无锁入队
    }
    
    void flush_loop() {
        while (running_) {
            QuoteTick tick;
            while (incoming_.pop(tick)) {
                buffer_.push_back(tick);
            }
            if (!buffer_.empty()) {
                send_batch(buffer_);  // 一次性 ZMQ 发送
                buffer_.clear();
            }
            std::this_thread::sleep_for(flush_interval_);
        }
    }
};
```

### 6.2 期权行情：改为异步事件 + 结果回传

如果 greeks_engine 计算结果需要返回，使用**异步事件**替代同步 Job：

```cpp
// 网关侧：发送计算请求，不阻塞
send_event("compute_greeks", tick, recipient_instance_id);

// greeks_engine 计算完成后，发送结果事件
send_event("greeks_result", result, recipient_gateway_id);

// 网关侧注册 on_greeks_result 处理结果
```

这样消除了 `request_event` 的阻塞等待，期权行情延迟降低到与期货相同量级。

---

## 7. 优化优先级与实施建议

| 优先级 | 优化项 | 预期收益 | 工作量 |
|--------|--------|---------|--------|
| P0 | 期权 `request_event` 改为异步 `send_event` | 消除 10ms+ 阻塞延迟 | 中 |
| P0 | `std::queue+mutex` 改为无锁队列 | 消除线程竞争，降低 5~20μs | 小 |
| P1 | `QuoteTick` 结构体替代 `Payload` | 消除堆分配，降低 20~50μs | 中 |
| P1 | 批量发送（每 1ms / 32 条） | 摊平序列化开销，提升吞吐量 3~5x | 中 |
| P2 | `tcp://` 改为 `ipc://`（同机） | 降低 30~50μs 网络延迟 | 小 |
| P2 | ZMQ 零拷贝发送 | 降低内存拷贝开销 | 小 |
| P3 | 共享内存（SHM）替代 ZMQ 跨进程通信 | 达到 <10μs 目标 | 大 |

---

## 8. 基于 MTS v3 HFT 实践的最终改进方案

### 核心原则：双路径设计

```
期货行情 → 零拷贝共享内存 → 无锁队列 → 立即发送（延迟优先）
期权行情 → SPSC无锁队列 → 微批量聚合 → 异步事件（吞吐优先）
```

### 改进 1：期货行情路径 — 共享内存零拷贝（P0）

参考 MTS v3 的 `BlockSharedQueue`，在 CTP 网关和引擎之间建立共享内存通道。

```cpp
// shm_quote.h — 共享内存行情结构
#pragma once
#include <atomic>
#include <cstdint>

struct ShmQuote {
    char instrument_id[32];
    char exchange_id[16];
    double last_price;
    int volume;
    double bid_price1;
    int bid_volume1;
    double ask_price1;
    int ask_volume1;
    double upper_limit_price;
    double lower_limit_price;
    double open_price;
    double high_price;
    double low_price;
    double pre_settle_price;
    double open_interest;
    double turnover;
    char update_time[16];
    int update_millisec;
    char trading_day[16];
    bool is_option;           // 预标记，避免运行时判断
    uint64_t seq;             // 序列号，用于丢包检测
};

// 环形缓冲区（无锁，单写单读）
template<size_t Capacity>
struct ShmRingBuffer {
    alignas(64) std::atomic<uint64_t> write_seq{0};
    alignas(64) std::atomic<uint64_t> read_seq{0};
    alignas(64) ShmQuote buffer[Capacity];

    bool push(const ShmQuote& q) {
        uint64_t seq = write_seq.load(std::memory_order_relaxed);
        if (seq - read_seq.load(std::memory_order_acquire) >= Capacity) {
            return false; // 满
        }
        buffer[seq % Capacity] = q;
        write_seq.store(seq + 1, std::memory_order_release);
        return true;
    }

    bool pop(ShmQuote& q) {
        uint64_t seq = read_seq.load(std::memory_order_relaxed);
        if (seq >= write_seq.load(std::memory_order_acquire)) {
            return false; // 空
        }
        q = buffer[seq % Capacity];
        read_seq.store(seq + 1, std::memory_order_release);
        return true;
    }
};
```

**CTP 网关侧修改**：

```cpp
// md_spi.cpp — OnRtnDepthMarketData 直接写共享内存
void MdSpiImpl::OnRtnDepthMarketData(CThostFtdcDepthMarketDataField* p) {
    if (!p) return;
    
    ShmQuote q;
    // 直接字段拷贝（无 string 构造，无 any，无 map）
    std::memcpy(q.instrument_id, p->InstrumentID, sizeof(p->InstrumentID));
    std::memcpy(q.exchange_id, p->ExchangeID, sizeof(p->ExchangeID));
    q.last_price = p->LastPrice;
    q.volume = p->Volume;
    // ... 其他字段直接拷贝
    
    // 预标记是否为期权（启动时已知的 option_instruments_ 用 hash set）
    q.is_option = option_instrument_set_.contains(
        std::string_view(p->InstrumentID, strnlen(p->InstrumentID, sizeof(p->InstrumentID))));
    
    // 无锁入队
    while (!shm_ring_buffer_->push(q)) {
        // 队列满：覆盖最旧（HFT 中丢弃旧数据比阻塞更好）
        ShmQuote dummy;
        shm_ring_buffer_->pop(dummy);
    }
}
```

**收益**：消除 `Payload` 构造、`serialize()`、ZMQ `tcp://` 三层开销，延迟从 **100~500μs** 降至 **<<5μs**。

### 改进 2：期权行情路径 — 无锁 SPSC 队列 + 异步微批量（P0）

```cpp
// 使用 moodycamel::ConcurrentQueue（MTS v3 实践验证）
#include "moodycamel/concurrentqueue.h"

class OptionDispatcher {
    static constexpr size_t BATCH_SIZE = 8;      // 微批量：8条
    static constexpr auto BATCH_TIMEOUT = std::chrono::microseconds(100); // 100μs
    
    moodycamel::ConcurrentQueue<ShmQuote> incoming_;  // 无锁，多生产者单消费者
    std::vector<ShmQuote> batch_;
    std::thread worker_;
    
public:
    void on_quote(const ShmQuote& q) {
        incoming_.enqueue(q);  // 无锁入队
    }
    
    void run() {
        while (running_) {
            ShmQuote q;
            auto start = std::chrono::steady_clock::now();
            
            // 批量收集：最多 BATCH_SIZE 条或 BATCH_TIMEOUT 超时
            while (batch_.size() < BATCH_SIZE && 
                   incoming_.try_dequeue(q)) {
                batch_.push_back(q);
            }
            
            if (!batch_.empty()) {
                // 异步发送：send_event 替代 request_event
                send_async_batch(batch_);
                batch_.clear();
            }
            
            // 精确睡眠到下一个 deadline，而非固定 20ms
            auto elapsed = std::chrono::steady_clock::now() - start;
            if (elapsed < BATCH_TIMEOUT) {
                std::this_thread::sleep_for(BATCH_TIMEOUT - elapsed);
            }
        }
    }
};
```

**关键变更**：`request_event` → `send_event("compute_greeks", ...)`，改为**异步事件**。

如果 greeks_engine 需要回传结果，增加反向事件通道：

```cpp
// greeks_engine 计算完成后发送
send_event("greeks_result", result, /*recipient=*/gateway_module_id);

// 网关注册 handler
_register_handler("greeks_result", [this](const Payload& p) {
    // 处理结果，无阻塞
});
```

**收益**：消除同步阻塞等待，期权延迟从 **10ms+** 降至 **<<100μs**（含微批量聚合）。

### 改进 3：行情线程 CPU 亲和性（P1）

```cpp
// 启动时绑定 CTP 回调线程到独立核心
void CtpGateway::start() {
    // ... 现有代码 ...
    
    // 绑核：行情线程独占一个物理核心
    option_dispatch_thread_ = std::thread([this]() {
        SetThreadAffinityMask(GetCurrentThread(), 1 << 2); // 绑定到 CPU 2
        // 可选：提升优先级
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
        option_dispatch_loop();
    });
}
```

### 改进 4：序列化精简 — 引擎端兼容层（P1）

共享内存方案需要引擎端增加 `ShmQuote` 读取适配。若短期内无法改造引擎，采用**分层序列化**：

```cpp
// 快速路径：ShmQuote → 紧凑二进制 → ZMQ（仅跨进程时）
std::array<uint8_t, sizeof(ShmQuote)> fast_serialize(const ShmQuote& q) {
    std::array<uint8_t, sizeof(ShmQuote)> buf;
    std::memcpy(buf.data(), &q, sizeof(ShmQuote));
    return buf;
}

// 慢速路径：兼容现有 Payload/msgpack（管理命令、非行情事件）
std::vector<uint8_t> legacy_serialize(const Payload& p) {
    return serialize(p);  // 现有 msgpack
}
```

在 `send_event` 中增加重载：

```cpp
// module.h
void send_event(const std::string& event, const ShmQuote& tick);
void send_event(const std::string& event, const Payload& payload, 
                std::optional<std::string> recipient = std::nullopt);
```

### 改进 5：期权合约判断 — 哈希集合替代二分查找（P1）

```cpp
// ctp_gateway.h
class CtpGateway : public tyche::TycheModule {
    // 替代 std::vector<std::string> option_instruments_;
    // 替代 std::binary_search
    absl::flat_hash_set<std::string> option_instrument_set_;
    // 或 std::unordered_set<std::string> option_instrument_set_;
};

// on_quote_received 中
bool is_option = option_instrument_set_.contains(instrument_id); // O(1)
```

**收益**：`O(log n)` → `O(1)`，字符串比较次数从 ~10 次降至 1 次（哈希）。

### 改进 6：ZMQ 发送锁优化 — 批量合并 + 减少锁持有时间（P2）

```cpp
// module.cpp — send_event 优化
void TycheModule::send_event(const std::string& event, const Payload& payload, ...) {
    // 预序列化到线程本地缓冲区（避免锁内序列化）
    thread_local msgpack::sbuffer buffer;
    buffer.clear();
    // ... 序列化到 buffer ...
    
    std::lock_guard<std::mutex> lock(_impl->pub_lock);
    // 锁内仅做 ZMQ send，最小化持有时间
    zmq::message_t topic(event.data(), event.size());
    zmq::message_t data(buffer.data(), buffer.size());
    _impl->pub_socket->send(topic, zmq::send_flags::sndmore);
    _impl->pub_socket->send(data, zmq::send_flags::none);
}
```

---

## 9. 实施路线图

| 阶段 | 内容 | 预期延迟 |
|------|------|---------|
| **Phase 1（1周）** | 期权 `request_event` → `send_event` 异步化 + `moodycamel::ConcurrentQueue` | 期权: 10ms → 100μs |
| **Phase 2（2周）** | 期货 `Payload` → `ShmQuote` + 共享内存环形缓冲区 | 期货: 500μs → 5μs |
| **Phase 3（1周）** | 引擎端 `ShmQuote` 适配 + 分层序列化 | 全链路兼容 |
| **Phase 4（1周）** | 线程绑核 + 哈希集合 + ZMQ 锁优化 | 稳定性提升 |

---

## 10. 与 MTS v3 架构的对照

| 设计点 | MTS v3 实践 | TycheEngine 改进方案 |
|--------|------------|---------------------|
| 行情跨进程传输 | `BlockSharedQueue`（共享内存） | 引入 `ShmRingBuffer` |
| 线程间事件队列 | `moodycamel::ConcurrentQueue` | 替换 `std::queue+mutex` |
| 数据格式 | `MarketData` 固定 struct（无动态分配） | `ShmQuote` 替代 `Payload` |
| 行情判断 | 启动时计算 `instrumentRef` | `option_instrument_set_` 哈希 |
| 线程调度 | 绑核 + `THREAD_PRIORITY_TIME_CRITICAL` | 增加绑核配置 |
| 序列化 | 共享内存零拷贝（同进程）/ 紧凑二进制（跨进程） | 分层序列化 |

---

## 11. 总结

当前 `ctp_gateway_cpp` 模块的延迟瓶颈主要集中在：

1. **期权同步 Job 模式**：`request_event` 阻塞分发线程，是最大延迟来源
2. **`std::any` + `std::unordered_map` 的通用 Payload 设计**：带来大量堆分配和类型擦除开销
3. **线程同步**：`mutex` + `condition_variable` 在高频行情下的竞争和唤醒延迟
4. **ZMQ `tcp://` 传输**：同机场景未利用 `ipc://` 或共享内存

要达到 README 中宣称的 `<10μs` 热路径延迟，需要：
- 将通用 `Payload` 改为固定结构体（如 `ShmQuote`）
- 使用无锁队列替代 `mutex`
- 期权改为异步事件模式
- 同机场景使用 `ipc://` 或共享内存替代 `tcp://`

如果保持当前架构（跨进程 + 通用 Payload + ZMQ tcp），实际延迟预计在 **100~500μs** 量级，距离 `<10μs` 目标有数量级差距。

按此最终方案实施后：
- **期货行情延迟**：`<<5μs`（共享内存零拷贝）
- **期权行情延迟**：`<<100μs`（无锁队列 + 异步微批量）
- **整体满足高性能交易系统要求**
