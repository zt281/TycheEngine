# CTP Gateway C++ 模块综合改进方案 v1

> 基于现有代码审计（2025-05-30）、延迟优化分析、以及 MTS v3 HFT 系统最佳实践，提出系统性改进方案。
> 编制日期：2026-06-13
> 目标：在保持现有功能正确性的前提下，提升 ctp_gateway_cpp 的**可靠性、可测试性、性能和可维护性**。

---

## 目录

1. [现状评估](#1-现状评估)
2. [改进目标](#2-改进目标)
3. [架构层改进](#3-架构层改进)
4. [可靠性改进](#4-可靠性改进)
5. [性能改进](#5-性能改进)
6. [可测试性改进](#6-可测试性改进)
7. [运维与可观测性改进](#7-运维与可观测性改进)
8. [实施路线图](#8-实施路线图)
9. [风险评估](#9-风险评估)

---

## 1. 现状评估

### 1.1 模块职责

`ctp_gateway_cpp` 是 TycheEngine 的 CTP 柜台网关模块，职责包括：
- 连接 CTP/TTS 前置服务器（MdApi 必选，TdApi 可选）
- 完成认证/登录流程
- 向 static_data 模块查询合约列表（期货+期权）
- 订阅行情并接收 `OnRtnDepthMarketData` 回调
- 混合路由：期货行情广播（`send_event`），期权行情 Job 分发（`request_event`）

### 1.2 代码量与结构

| 文件 | 行数 | 职责 |
|------|------|------|
| `ctp_gateway.h/cpp` | ~85+404 | 网关主类、生命周期、混合路由 |
| `md_spi.h/cpp` | ~67+185 | 行情 SPI：连接→登录→订阅→行情转换 |
| `td_spi.h/cpp` | ~54+140 | 交易 SPI：认证→登录→阻塞等待 |
| `config.h/cpp` | ~84+89 | 配置加载与校验、secure_string |
| `ctp_loader.h/cpp` | ~56+282 | 跨平台 DLL 动态加载 |
| `main.cpp` | 113 | 入口点、信号处理 |
| **合计** | **~1559** | — |

### 1.3 已完成的优化

根据 2025-05-30 审计报告，已修复 17 项 CRITICAL/HIGH/MEDIUM 问题：
- 内存安全（`safe_copy`、`zero_password_field`、`safe_string`）
- 线程安全（`atomic` 标志、`condition_variable`、双重停止防护）
- 异常安全（`noexcept cleanup_ctp`、try-catch 分层）
- DLL 安全（路径验证、PE 导出表边界检查）
- 配置校验（必填字段、端口范围、超时值）

### 1.4 待解决的核心问题

| 类别 | 问题 | 影响 |
|------|------|------|
| 性能 | `Payload`（`unordered_map<string, any>`）堆分配密集 | 每 tick ~20+ 次堆分配 |
| 性能 | 期权 `request_event` 同步阻塞 10s 超时 | 吞吐量受限于单条处理延迟 |
| 性能 | `tcp://` loopback 传输同机行情 | ~100μs 额外延迟 |
| 可靠性 | 无自动重连/重订阅机制（依赖 CTP SDK 内部重连） | 网络闪断后状态不确定 |
| 可靠性 | 无行情数据校验（如价格合理性、时间戳连续性） | 异常行情透传下游 |
| 可测试性 | 零 C++ 单元测试 | 回归风险不可控 |
| 可测试性 | CTP API 无 mock 接口 | 无法离线测试 SPI 逻辑 |
| 可维护性 | DLL 句柄泄漏（从未 FreeLibrary） | 长期运行资源泄漏 |
| 可维护性 | 日志无结构化输出 | 难以自动化分析 |
| 可观测性 | 无延迟/吞吐量指标暴露 | 无法监控实时性能 |

---

## 2. 改进目标

| 维度 | 目标 | 指标 |
|------|------|------|
| 延迟 | 期货行情端到端 < 100μs（同机） | P99 延迟实测 |
| 延迟 | 期权分发非阻塞，< 1ms | 消除同步等待 |
| 吞吐量 | 支持 ≥50,000 ticks/s 持续发送 | 压测验证 |
| 可靠性 | 网络闪断后 30s 内自动恢复 | 断线模拟测试 |
| 可靠性 | 异常行情检测与过滤 | 价格跳变 >10% 过滤日志 |
| 可测试性 | 核心逻辑 ≥ 80% 行覆盖率 | C++ 单元测试 |
| 可观测性 | 延迟 P50/P99/Max 指标实时暴露 | Admin 接口查询 |

---

## 3. 架构层改进

### 3.1 引入 CTP API 抽象层

**问题**：当前直接使用 `CThostFtdcMdApi*`/`CThostFtdcTraderApi*` 裸指针，且 SPI 回调直接耦合业务逻辑。

**方案**：引入接口抽象层，将 CTP API 依赖隔离到适配器中。

```cpp
// ictp_md_api.h — 行情 API 抽象接口
class ICtpMdApi {
public:
    virtual ~ICtpMdApi() = default;
    virtual int RegisterFront(char* front_addr) = 0;
    virtual void RegisterSpi(CThostFtdcMdSpi* spi) = 0;
    virtual void Init() = 0;
    virtual void Join() = 0;
    virtual void Release() = 0;
    virtual int SubscribeMarketData(char** instruments, int count) = 0;
    virtual int ReqUserLogin(CThostFtdcReqUserLoginField* req, int id) = 0;
};

// ctp_md_api_adapter.h — 真实 CTP 适配器
class CtpMdApiAdapter : public ICtpMdApi {
    CThostFtdcMdApi* api_;
public:
    explicit CtpMdApiAdapter(CThostFtdcMdApi* api) : api_(api) {}
    int RegisterFront(char* addr) override { return api_->RegisterFront(addr); }
    // ...
};

// mock_md_api.h — 测试用 mock
class MockMdApi : public ICtpMdApi {
    // gmock 或手工 mock
};
```

**收益**：
- MdSpi/TdSpi 可独立单元测试
- 支持模拟交易所行为（延迟注入、异常注入）
- 为未来支持其他行情源（如内存行情回放）打下基础

### 3.2 RAII 资源管理

**问题**：CTP API 对象使用裸指针，释放逻辑散落在 `cleanup_ctp()`。

**方案**：使用自定义 RAII 包装器。

```cpp
// ctp_api_raii.h
struct MdApiDeleter {
    void operator()(CThostFtdcMdApi* api) noexcept {
        if (api) {
            api->RegisterSpi(nullptr);
            api->Join();
            api->Release();
        }
    }
};
using MdApiPtr = std::unique_ptr<CThostFtdcMdApi, MdApiDeleter>;

struct TdApiDeleter {
    void operator()(CThostFtdcTraderApi* api) noexcept {
        if (api) {
            api->RegisterSpi(nullptr);
            api->Join();
            api->Release();
        }
    }
};
using TdApiPtr = std::unique_ptr<CThostFtdcTraderApi, TdApiDeleter>;
```

**收益**：
- 异常安全：任何路径退出都自动清理
- 消除 `cleanup_done_` 标志和手动清理逻辑
- 代码简化约 40 行

### 3.3 期权分发改为异步事件模式

**问题**：`request_event("compute_greeks", tick, 10.0f)` 同步阻塞分发线程。

**方案**：改为 `send_event` + 点对点路由，greeks_engine 侧异步处理。

```
当前：
  CTP回调 → option_queue_ → dispatch线程 → request_event(阻塞10s) → greeks_engine → response回传

改进后：
  CTP回调 → option_queue_ → dispatch线程 → send_event("compute_greeks", tick) → greeks_engine（异步处理）
                                                                                        ↓
                                                                                  send_event("greeks_result", result) → [需要时监听]
```

**关键变更**：
- `_register_producer("request_compute_greeks", ...)` → `_register_producer("send_compute_greeks", ...)`
- `option_dispatch_loop()` 中 `request_event` → `send_event`
- greeks_engine 侧需对应修改为 `on_compute_greeks` 消费者模式

**收益**：
- 消除 10s 超时阻塞
- 单线程吞吐量从 ~100 ticks/s 提升到 ~50,000 ticks/s
- 分发线程失败不会影响主线程

### 3.4 引入 QuoteTick POD 结构体

**问题**：`Payload`（`unordered_map<string, any>`）在行情热路径上大量堆分配。

**方案**：定义 POD 结构体用于内部传输，仅在发送到 ZMQ 时序列化。

```cpp
// quote_tick.h — 行情 POD 结构体（零堆分配）
#pragma once
#include <cstdint>

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
    uint64_t receive_ts_ns;  // 收到时间戳（纳秒），用于延迟计量
};
```

**使用方式**：
- `OnRtnDepthMarketData` 直接填充 `QuoteTick`（无 string/any 构造）
- 路由判断后，仅在 `send_event` 时转换为 `Payload`（或使用二进制快速路径）
- 期权队列 `std::queue<QuoteTick>` 替代 `std::queue<Payload>`

**收益**：每 tick 堆分配从 ~20 次降至 0 次（路由判断路径）。

---

## 4. 可靠性改进

### 4.1 行情断线自动重订阅

**问题**：CTP SDK 内部会自动重连，但重连后需要重新订阅才能恢复行情。

**当前行为**：`OnFrontConnected()` → `do_login()` → `OnRspUserLogin()` → `do_subscribe()`

**改进**：增加重连计数与状态监控。

```cpp
// md_spi.h 新增
class MdSpiImpl : public CThostFtdcMdSpi {
    std::atomic<int> reconnect_count_{0};
    std::atomic<int> subscribe_fail_count_{0};
    std::chrono::steady_clock::time_point last_tick_time_;
    std::atomic<bool> tick_stale_{false};  // 超过 30s 无行情视为 stale
    // ...
};
```

**新增 stale 检测**：分发线程每 30s 检查最后行情时间，若超时则标记 stale 并触发告警。

### 4.2 行情数据异常检测

参考 MTS v3 的 `CheckMarketDataAbnormal()`，在行情入口增加异常过滤：

```cpp
// quote_validator.h
struct QuoteValidator {
    // 价格跳变超过 10% 视为异常（涨跌停除外）
    static constexpr double MAX_PRICE_JUMP_RATIO = 0.10;

    bool validate(const QuoteTick& tick, const QuoteTick& prev) const {
        if (prev.last_price <= 0) return true;  // 无前值，通过

        double ratio = std::abs(tick.last_price - prev.last_price) / prev.last_price;
        if (ratio > MAX_PRICE_JUMP_RATIO) {
            // 检查是否在涨跌停板内
            if (tick.last_price > tick.upper_limit_price ||
                tick.last_price < tick.lower_limit_price) {
                return false;  // 超出涨跌停，异常
            }
        }

        // 时间戳倒退检测
        // Volume 递减检测（除非跨交易日）
        return true;
    }
};
```

### 4.3 优雅降级策略

| 场景 | 当前行为 | 改进后行为 |
|------|----------|------------|
| static_data 超时 | 重试 12 次后用空列表继续 | 重试后进入 degraded 模式，定期重新尝试 |
| greeks_engine 不可用 | 期权 Job 超时报错后静默 | 切换为广播模式，待恢复后自动切回 Job |
| MdApi 登录失败 | 抛异常终止 | 根据 ErrorID 判断是否可重试 |
| 行情断流 30s | 无感知 | 触发 stale 告警，上报 admin 接口 |

### 4.4 DLL 句柄生命周期管理

**问题**：`open_lib()` 加载的 DLL 从未释放。

**方案**：引入 `DllHandle` RAII 类，在 `CtpGateway` 析构时自动释放。

```cpp
// dll_handle.h
class DllHandle {
    void* handle_ = nullptr;
public:
    explicit DllHandle(void* h) : handle_(h) {}
    ~DllHandle() {
        if (handle_) {
#ifdef _WIN32
            FreeLibrary(reinterpret_cast<HMODULE>(handle_));
#else
            dlclose(handle_);
#endif
        }
    }
    void* get() const { return handle_; }
    // 移动语义支持
    DllHandle(DllHandle&& other) noexcept : handle_(other.handle_) { other.handle_ = nullptr; }
    DllHandle& operator=(DllHandle&& other) noexcept;
    DllHandle(const DllHandle&) = delete;
};
```

**注意**：CTP API 对象的生命周期依赖 DLL，需确保释放顺序为 API → DLL。

---

## 5. 性能改进

### 5.1 无锁队列替代 mutex + queue

**问题**：`option_queue_` 使用 `std::queue + mutex + condition_variable`，每次入/出队加锁。

**方案**：使用 SPSC 无锁队列（单生产者单消费者），CTP 回调线程为唯一写者。

```cpp
// 使用项目已有的 ring_buffer（src/tyche/cpp/engine/ring_buffer.h）
// 或引入 moodycamel::ConcurrentQueue
#include "tyche/cpp/engine/ring_buffer.h"

// ctp_gateway.h
tyche::RingBuffer<QuoteTick, 65536> option_ring_buffer_;
```

**收益**：入队延迟从 ~5μs（mutex 竞争）降至 ~50ns（atomic store）。

### 5.2 期权合约判断优化

**问题**：`std::binary_search` 在排序 vector 上 O(log n) 次字符串比较。

**方案**：使用 `std::unordered_set<std::string>` 或 `absl::flat_hash_set`。

```cpp
// ctp_gateway.h — 替换
std::unordered_set<std::string> option_instrument_set_;

// 也可用 string_view + 固定 buffer 避免 string 构造
// 基于 instrument_id 为固定长度 char[31]，可用 FNV-1a 哈希
```

**进一步优化**：在 `OnRtnDepthMarketData` 中直接用 `string_view` 查找，避免 `std::string` 构造。

```cpp
bool is_option = option_instrument_set_.count(
    std::string(p->InstrumentID, strnlen(p->InstrumentID, sizeof(p->InstrumentID)))) > 0;
```

### 5.3 send_event 序列化预计算

**问题**：每次 `send_event` 都会重新序列化 topic 字符串为 `zmq::message_t`。

**方案**：对固定 topic（如 "quote"）预构造 ZMQ 消息帧。

```cpp
// ctp_gateway.h
zmq::message_t cached_quote_topic_;  // 构造函数中初始化

// start() 中
cached_quote_topic_ = zmq::message_t("quote", 5);
```

### 5.4 微批量发送（可选，Phase 2）

对高频行情（如 500+ 合约同时活跃），每 500μs 收集一批行情统一序列化和发送：

```
CTP回调 → QuoteTick入队(无锁) → FlushThread每500μs批量取出 → 一次ZMQ multipart发送
```

**适用场景**：合约数 > 200 时启用；合约数少时直接发送延迟更低。

---

## 6. 可测试性改进

### 6.1 单元测试覆盖计划

| 测试文件 | 覆盖目标 | 优先级 |
|----------|----------|--------|
| `test_config.cpp` | JSON 解析、必填字段校验、边界值 | P0 |
| `test_ctp_loader.cpp` | DLL 路径验证、resolve_md/td_dll、路径拼接 | P0 |
| `test_quote_routing.cpp` | 混合路由逻辑（期货/期权分支） | P0 |
| `test_extract_instrument_ids.cpp` | 响应解析、异常格式处理 | P1 |
| `test_md_spi_logic.cpp` | depth_to_payload 转换、safe_string | P1 |
| `test_option_dispatch.cpp` | 队列满丢弃、优雅停止、错误抑制 | P1 |
| `test_quote_validator.cpp` | 价格跳变、时间戳倒退 | P2 |

### 6.2 测试基础设施

**依赖**：使用项目已有的 CMake 测试目标（`tests/cpp/CMakeLists.txt`）。

**Mock 策略**：
- CTP API 接口通过 `ICtpMdApi` 抽象层 mock
- TycheModule 的 `send_event`/`request_event` 通过继承 override 拦截
- 配置加载使用临时 JSON 文件

### 6.3 集成测试

使用 OpenCTP 7x24 模拟平台进行端到端测试：

```
test_integration_ctp_gateway.py:
  1. 启动 TycheEngine
  2. 启动 static_data 模块
  3. 启动 ctp_gateway_cpp（连接 OpenCTP）
  4. 验证 30s 内收到行情事件
  5. 模拟网络断开（kill front port forwarding）
  6. 验证 60s 内自动恢复行情
```

---

## 7. 运维与可观测性改进

### 7.1 结构化日志

**问题**：当前使用 `std::cout`/`std::cerr` 非结构化输出。

**方案**：引入轻量级 JSON 日志格式（或沿用 `spdlog`）。

```cpp
// 建议格式
// {"ts":"2026-06-13T15:30:01.123","level":"INFO","module":"CtpGateway","msg":"Login OK","trading_day":"20260613"}

// 最小改动方案：统一前缀格式
#define LOG_INFO(fmt, ...)  std::cout << "[" << timestamp() << "][INFO][CtpGateway] " << fmt << "\n"
#define LOG_WARN(fmt, ...)  std::cerr << "[" << timestamp() << "][WARN][CtpGateway] " << fmt << "\n"
#define LOG_ERROR(fmt, ...) std::cerr << "[" << timestamp() << "][ERROR][CtpGateway] " << fmt << "\n"
```

### 7.2 性能指标暴露

通过 TycheEngine 的 Admin 接口暴露关键指标：

| 指标 | 类型 | 说明 |
|------|------|------|
| `gateway.ticks_received` | counter | 收到的行情总数 |
| `gateway.ticks_sent` | counter | 已发送（期货广播）的行情数 |
| `gateway.option_queue_depth` | gauge | 期权队列当前深度 |
| `gateway.option_dropped` | counter | 期权队列溢出丢弃数 |
| `gateway.option_errors` | counter | 期权分发失败数 |
| `gateway.latency_ns.p50` | histogram | 行情处理延迟 P50 |
| `gateway.latency_ns.p99` | histogram | 行情处理延迟 P99 |
| `gateway.reconnect_count` | counter | 重连次数 |
| `gateway.last_tick_age_ms` | gauge | 最后行情距今时间（stale 检测） |

### 7.3 健康检查与 Admin 命令

注册 `handle_status` Job，响应 TUI 或引擎的健康检查请求：

```cpp
_register_job_handler("gateway_status", [this](const Payload& req) -> Payload {
    Payload resp;
    resp["status"] = ctp_running_.load() ? std::string("running") : std::string("stopped");
    resp["instruments_count"] = static_cast<int>(instruments_.size());
    resp["option_queue_depth"] = static_cast<int>(option_queue_.size());
    resp["reconnect_count"] = reconnect_count_.load();
    resp["ticks_received"] = ticks_received_.load();
    resp["uptime_secs"] = elapsed_since_start();
    return resp;
});
```

### 7.4 配置热更新（长期）

参考 MTS v3 的 XML 热更新机制，支持运行时修改配置（如添加品种、调整重试参数）而无需重启：

```
Admin命令 "reload_config" → 重新读取 JSON → diff 差异 → 增量订阅新合约
```

---

## 8. 实施路线图

### Phase 1：可测试性基础（1 周）

| Task | 内容 | 产出 |
|------|------|------|
| 1.1 | 定义 `ICtpMdApi`/`ICtpTdApi` 接口 | `ictp_api.h` |
| 1.2 | 实现真实 API 适配器 | `ctp_md_api_adapter.h/cpp` |
| 1.3 | 重构 MdSpi/TdSpi 使用接口 | 修改 `md_spi.h/cpp`, `td_spi.h/cpp` |
| 1.4 | 编写 `test_config.cpp` | 覆盖配置加载校验 |
| 1.5 | 编写 `test_ctp_loader.cpp` | 覆盖路径验证逻辑 |

### Phase 2：性能基础（1 周）

| Task | 内容 | 产出 |
|------|------|------|
| 2.1 | 定义 `QuoteTick` POD 结构体 | `quote_tick.h` |
| 2.2 | `depth_to_payload` → `depth_to_tick` 改造 | 修改 `md_spi.cpp` |
| 2.3 | `option_queue_` 改用项目已有 `RingBuffer` | 修改 `ctp_gateway.h/cpp` |
| 2.4 | `option_instruments_` 改用 `unordered_set` | 修改 `ctp_gateway.h/cpp` |
| 2.5 | 编写 `test_quote_routing.cpp` | 验证路由正确性 |

### Phase 3：可靠性增强（1 周）

| Task | 内容 | 产出 |
|------|------|------|
| 3.1 | 引入 `QuoteValidator` 异常行情检测 | `quote_validator.h` |
| 3.2 | 实现行情 stale 检测 | 修改 `ctp_gateway.cpp` |
| 3.3 | CTP API RAII 包装器 | `ctp_api_raii.h` |
| 3.4 | DLL 句柄 RAII 管理 | `dll_handle.h`, 修改 `ctp_loader.cpp` |
| 3.5 | 优雅降级：greeks_engine 不可用时 fallback | 修改 `option_dispatch_loop` |

### Phase 4：期权异步化 + 可观测性（1 周）

| Task | 内容 | 产出 |
|------|------|------|
| 4.1 | 期权 `request_event` → `send_event` 改造 | 修改 `ctp_gateway.cpp` |
| 4.2 | greeks_engine 对应消费者接口适配 | 修改 `greeks_engine.py` |
| 4.3 | 注册 `handle_gateway_status` 健康检查 | 修改 `ctp_gateway.cpp` |
| 4.4 | 添加性能计数器（ticks_received 等） | 修改 `ctp_gateway.h/cpp` |
| 4.5 | 结构化日志宏 | `gateway_log.h` |

### Phase 5：高级性能优化（可选，2 周）

| Task | 内容 | 产出 |
|------|------|------|
| 5.1 | 微批量发送策略 | `quote_batcher.h` |
| 5.2 | `ipc://` 替代 `tcp://` 同机通信 | 修改 `module.cpp`（引擎层） |
| 5.3 | CPU 亲和性配置 | 配置项 + 启动绑核逻辑 |
| 5.4 | 共享内存行情通道（ShmRingBuffer） | 新模块，需引擎侧配合 |

---

## 9. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| CTP API 接口抽象导致性能下降 | 低 | 低 | 虚函数开销 ~1ns，远低于 ZMQ 传输 |
| 期权异步化后 greeks_engine 兼容性 | 中 | 中 | Phase 4 与 greeks_engine 同步改造 |
| 无锁队列引入内存序 bug | 低 | 高 | 使用验证过的 RingBuffer 实现 + 压测 |
| 测试基础设施搭建成本 | 低 | 低 | 复用项目已有 CMake 测试框架 |
| DLL 卸载时序不当导致 crash | 中 | 高 | 确保 CTP API Release() 在 DLL 卸载之前 |
| 行情校验误过滤正常涨跌停行情 | 中 | 中 | 对比涨跌停板价，限价内允许通过 |

---

## 附录 A：与 MTS v3 的对照表

| 设计点 | MTS v3 HFT 实践 | 当前 ctp_gateway_cpp | 改进目标 |
|--------|-----------------|---------------------|----------|
| 行情数据结构 | `MarketData` 固定 struct | `Payload`（动态 map） | `QuoteTick` POD |
| 行情跨进程传输 | `BlockSharedQueue` 共享内存 | ZMQ `tcp://` | Phase 5 SHM |
| 期权/期货判断 | 启动时 `instrumentRef` 直接索引 | `binary_search` on vector | `unordered_set` O(1) |
| 线程间队列 | `moodycamel::ConcurrentQueue` | `std::queue + mutex` | `RingBuffer` 无锁 |
| 行情异常检测 | `CheckMarketDataAbnormal()` | 无 | `QuoteValidator` |
| 风控限流 | FAK/GFD 发单数静态限制 | N/A（网关不下单） | 行情频率监控 |
| 日志系统 | nanolog（二进制高性能） | cout/cerr | 结构化 JSON 日志 |
| 策略热加载 | `SoManager` → `.so` | N/A | 未来模块热更新 |
| 线程绑核 | 行情线程独占物理核 | 无 | Phase 5 CPU affinity |

---

## 附录 B：文件变更预览

```
src/modules/ctp_gateway_cpp/
├── src/
│   ├── ctp_gateway.h         [修改] 新增 unordered_set、QuoteTick 队列、计数器
│   ├── ctp_gateway.cpp       [修改] 异步分发、QuoteTick、性能计数
│   ├── md_spi.h              [修改] 使用 ICtpMdApi 接口
│   ├── md_spi.cpp            [修改] depth_to_tick、stale 检测
│   ├── td_spi.h              [修改] 使用 ICtpTdApi 接口
│   ├── td_spi.cpp            [微调] 适配接口
│   ├── config.h              [不变]
│   ├── config.cpp            [不变]
│   ├── ctp_loader.h          [修改] 返回 DllHandle + API ptr
│   ├── ctp_loader.cpp        [修改] DllHandle RAII
│   ├── main.cpp              [不变]
│   ├── ictp_api.h            [新增] CTP API 抽象接口
│   ├── ctp_api_adapter.h     [新增] 真实 CTP 适配器
│   ├── ctp_api_raii.h        [新增] RAII 包装器
│   ├── quote_tick.h          [新增] POD 行情结构体
│   ├── quote_validator.h     [新增] 行情异常检测
│   ├── dll_handle.h          [新增] DLL 句柄 RAII
│   └── gateway_log.h         [新增] 结构化日志宏
├── tests/
│   ├── test_config.cpp       [新增]
│   ├── test_ctp_loader.cpp   [新增]
│   ├── test_quote_routing.cpp [新增]
│   └── test_quote_validator.cpp [新增]
└── CMakeLists.txt            [修改] 新增测试目标
```

---

## 附录 C：参考资料

- `docs/impl/ctp_gateway_cpp_audit_2025-05-30.md` — 安全与正确性审计
- `docs/impl/ctp_gateway_cpp_latency_optimization.md` — 延迟优化专项分析
- `docs/impl/cpp_build_guide.md` — C++ 构建指南
- MTS v3 HFT 系统架构（cpp-hft-system skill reference）
