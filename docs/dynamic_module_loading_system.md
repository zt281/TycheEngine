# TycheEngine 跨平台动态模块加载系统 — 技术方案与可行性分析

## 文档信息

- **版本**: v1.0
- **日期**: 2026-06-21
- **作者**: TycheEngine 架构团队
- **状态**: APPROVED

---

## 1. 系统架构总览

TycheEngine 的跨平台动态模块加载系统采用三层架构：

```
┌──────────────────────────────────────────────────────────────────┐
│                      TycheEngine (Core)                          │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │  ZMQ Event Bus  │◄───│      SharedMemoryBridge              │ │
│  │ XPUB/XSUB Proxy │    │  ┌────────────────────────────────┐ │ │
│  │                  │    │  │ Worker Loop (polling thread)    │ │ │
│  └─────────────────┘    │  │  - poll module queues           │ │ │
│                          │  │  - poll raw bridge queues       │ │ │
│                          │  │  - forward → inject_event_raw() │ │ │
│                          │  └────────────────────────────────┘ │ │
│                          └─────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
         ▲                           ▲
         │ ZMQ Socket                │ Shared Memory (SPSC Ring Buffer)
         │                           │
┌────────┴─────────┐     ┌──────────┴────────────────────────────┐
│ Python/Rust/C++  │     │    DLL/SO Module (extern "C")          │
│ ZMQ Modules      │     │  tyche_module_init(shm_queue_name)     │
│                  │     │  tyche_module_run()                     │
│                  │     │  tyche_module_stop()                    │
│                  │     │  tyche_module_get_interfaces()          │
└──────────────────┘     └────────────────────────────────────────┘
```

---

## 2. 跨平台兼容性分析

### 2.1 DynamicLibrary — 已完整实现

| 特性 | Windows | Linux | 状态 |
|------|---------|-------|------|
| 加载 | `LoadLibraryA()` | `dlopen(RTLD_NOW \| RTLD_LOCAL)` | ✅ |
| 符号查找 | `GetProcAddress()` | `dlsym()` | ✅ |
| 卸载 | `FreeLibrary()` | `dlclose()` | ✅ |
| 错误报告 | `FormatMessageA(GetLastError())` | `dlerror()` | ✅ |
| RAII封装 | move语义 + unique_ptr<Impl> | 同左 | ✅ |

**关键设计决策**：
- `RTLD_LOCAL` 避免符号污染，防止多个模块间符号冲突
- `RTLD_NOW` 确保加载时即刻解析所有符号，fail-fast 优于 lazy binding
- pimpl 模式隔离平台差异，头文件无平台条件编译

### 2.2 SharedMemoryQueue — 已完整实现

| 特性 | Windows | Linux | 状态 |
|------|---------|-------|------|
| 创建 | `CreateFileMappingA` | `shm_open + ftruncate` | ✅ |
| 打开 | `OpenFileMappingA` | `shm_open(O_RDWR)` | ✅ |
| 映射 | `MapViewOfFile` | `mmap(MAP_SHARED)` | ✅ |
| 销毁 | `UnmapViewOfFile + CloseHandle` | `munmap + shm_unlink` | ✅ |
| 命名 | `"tyche_shm_" + name` | `"/tyche_shm_" + name` | ✅ |

**设计优点**：
- SPSC ring buffer 带 sequence-number 同步（LMAX Disruptor 模式）
- 64-byte Header 保证 cache line 对齐
- 无锁写入（CAS-based），单生产者无争用

### 2.3 潜在平台差异

1. **Windows DLL 导出符号**：
   - 默认不导出，需 `__declspec(dllexport)` 或 `.def` 文件
   - 建议：模块使用 `extern "C"` + `__declspec(dllexport)`，不使用 `WINDOWS_EXPORT_ALL_SYMBOLS`

2. **SHM 命名约束**：
   - Linux `shm_open` 名称最大 255 字符，仅允许一个前导 `/`
   - 当前 `"/tyche_shm_" + name` 格式正确

3. **路径分隔符**：
   - `DynamicLibrary` 使用 `std::string` 接收路径
   - 建议统一使用 `/`，Windows `LoadLibraryA` 也支持

---

## 3. 共享内存通信性能分析

### 3.1 延迟特征

| 路径 | 预期延迟 | 分析 |
|------|----------|------|
| SHM raw memcpy (flat struct) | **~5-15ns/op** | 仅 memcpy，无序列化 |
| SHM + msgpack serialize | **~200-500ns/op** | msgpack 编码 + 堆分配 |
| SHM → ZMQ inject_event_raw | **~50-100ns** | 入队 + condition_variable notify |
| ZMQ 端到端 (pub/sub) | **~10-50μs** | TCP 栈 + 内核态切换 |

**关键洞察**：`inject_event_raw()` 绕过 msgpack 序列化，直接作为 Frame 入队。高频行情场景比纯 ZMQ 路径快 100-1000x。

### 3.2 吞吐量分析

- SPSC Ring Buffer 容量：1024 slots × 64KB/slot = **64MB 缓冲区**
- 无锁写入（CAS），单生产者无争用
- Worker loop 无消息时 `sleep_for(1ms)`，有消息时 busy drain

**瓶颈点**：Worker loop 持有 `_modules_lock` mutex 遍历模块。模块数量 >10 时可能影响延迟。

---

## 4. 模块热加载/卸载安全性分析

### 4.1 当前安全保障

| 安全措施 | 实现方式 | 评价 |
|----------|----------|------|
| 独立线程 | `tyche_module_run()` 在独立 `std::thread` 中执行 | ✅ 隔离崩溃不影响主线程 |
| 生命周期管理 | `stop_fn()` → `join()` → `erase()` 有序 | ✅ |
| 异常隔离 | `try { mod.stop_fn(); } catch (...) {}` | ✅ 防止 DLL 异常传播 |
| RAII 卸载 | `unique_ptr<DynamicLibrary>` 析构自动 FreeLibrary/dlclose | ✅ |

### 4.2 风险点与改进建议

#### 风险 1：Worker 竞争

`unload_module()` 获取 `_modules_lock` 后删除模块。`_worker_loop()` 也在 lock 下遍历 `_modules`。如果 worker 正在 `mod.queue->read()` 内部（lock 已释放），指针仍然有效。

**结论**：当前实现安全。

#### 风险 2：run_thread join 阻塞

如果 `tyche_module_run()` 不响应 `tyche_module_stop()`，`join()` 会无限阻塞。

**改进建议**：增加超时机制

```cpp
void SharedMemoryBridge::unload_module(const std::string& shm_queue_name) {
    std::lock_guard lock(_modules_lock);
    auto it = _modules.find(shm_queue_name);
    if (it != _modules.end()) {
        if (it->second.stop_fn) {
            try { it->second.stop_fn(); } catch (...) {}
        }
        if (it->second.run_thread.joinable()) {
            // 超时 join — 防止恶意模块阻塞引擎
            auto future = std::async(std::launch::async, [&]() {
                it->second.run_thread.join();
            });
            if (future.wait_for(std::chrono::seconds(5)) == std::future_status::timeout) {
                it->second.run_thread.detach(); // 泄漏线程但不阻塞引擎
                // LOG_WARNING: module failed to stop within timeout
            }
        }
        _modules.erase(it);
    }
}
```

#### 风险 3：DLL 卸载后残留引用

`FreeLibrary/dlclose` 后，如果 `run_thread` 仍在执行模块代码（detach 场景），会导致 segfault。

**结论**：所有动态模块系统的本质风险。必须确保 `tyche_module_run()` 已返回后再卸载。

---

## 5. 内存管理和资源泄漏防护

### 5.1 已有 RAII 保护

| 资源 | 保护方式 | 评价 |
|------|----------|------|
| DynamicLibrary | `unique_ptr<DynamicLibrary>` | ✅ |
| SharedMemoryQueue | `unique_ptr<SharedMemoryQueue>` + owner 析构 | ✅ |
| 线程 | `~SharedMemoryBridge()` 调用 `stop()` | ✅ |
| ZMQ 上下文 | 引擎管理 | ✅ |

### 5.2 潜在泄漏场景

1. **SHM segment 残留（Linux）**：
   - 进程异常终止（SIGKILL），`shm_unlink` 不会执行
   - `/dev/shm/tyche_shm_*` 文件残留
   - **建议**：引擎启动时扫描并清理旧的 SHM segments

2. **Windows FileMapping 残留**：
   - 内核对象在最后一个 handle 关闭时自动清理
   - 比 Linux 更安全（引用计数）

3. **`std::vector<uint8_t>` 在 read() 中**：
   - 每次 `read()` 分配新 vector
   - **建议**：提供 `read_into(buffer)` 接口，零分配路径

---

## 6. 错误处理和异常恢复机制

### 6.1 当前错误处理

| 错误场景 | 处理方式 | 评价 |
|----------|----------|------|
| DLL 加载失败 | 返回空 module_id + stderr 日志 | ✅ 优雅降级 |
| 缺少必要符号 | 返回空 module_id | ✅ |
| init 失败（返回非0） | 返回空 module_id | ✅ |
| Queue 创建失败 | 返回空 module_id / skip bridge | ✅ |
| 消息解析失败（topic 为空） | stderr 警告 + 跳过 | ✅ |
| 模块 run 崩溃 | 线程异常终止 + 日志 | ⚠️ 无自动恢复 |

### 6.2 建议增强的恢复机制

建议引入模块健康状态机：

```
LOADING → INITIALIZING → RUNNING → STOPPING
   │           │            │
   ▼           ▼            ▼
FAILED    INIT_FAILED  CRASHED → RESTARTING → RUNNING
```

增强措施：
- **崩溃检测**：监控 `run_thread` 是否提前退出
- **自动重启**：指数退避重试（1s/2s/4s/8s，最大3次）
- **死信处理**：模块崩溃期间消息转入 dead_letter_store

---

## 7. 综合可行性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 跨平台兼容性 | ⭐⭐⭐⭐⭐ | 已完整实现 Win/Linux 双平台，pimpl 隔离平台差异 |
| 性能开销 | ⭐⭐⭐⭐☆ | SHM SPSC < 100ns，worker loop mutex + sleep(1ms) 有优化空间 |
| 热加载安全 | ⭐⭐⭐⭐☆ | RAII + 有序 stop，但缺少超时保护和崩溃恢复 |
| 内存管理 | ⭐⭐⭐⭐☆ | RAII 覆盖全面，Linux SHM 残留需处理 |
| 错误处理 | ⭐⭐⭐☆☆ | 错误检测完整，恢复机制需增强 |
| 可维护性 | ⭐⭐⭐⭐⭐ | 接口简洁（4个 C 函数），stub 测试完备 |

---

## 8. 优化路线图

### P0 — 生产必需

1. **模块停止超时机制**（代码见第4.2节）
2. **Linux SHM 清理**：启动时 `glob("/dev/shm/tyche_shm_*")` 并 unlink 旧文件
3. **模块版本验证**：在 `module_interface.h` 增加 `tyche_module_version()` 导出

### P1 — 性能关键

4. **Worker loop 改为 adaptive spin**：将 `sleep_for(1ms)` 替换为 adaptive spin，延迟从 ms 级降至 μs 级
5. **Read 零分配**：提供 `read_into(buffer)` 接口，高频路径避免 heap 分配
6. **锁分离**：将 `_modules_lock` 改为 per-module 读写锁或 RCU 快照

### P2 — 可观测性

7. **模块状态上报**：通过 heartbeat 机制暴露 alive/crashed/restarting 状态
8. **性能指标**：记录每个模块的消息吞吐量和队列深度，暴露给 TUI

---

## 9. 模块接口规范

当前 `module_interface.h` 定义的4个函数 ABI 是稳定且完备的：

```c
int  tyche_module_init(const char* shm_queue_name);   // 初始化，传入队列名
int  tyche_module_run(void);                           // 阻塞运行
void tyche_module_stop(void);                          // 信号停止
const char* tyche_module_get_interfaces(void);         // 声明事件接口
```

**设计优点**：
- 纯 C ABI，无 C++ name mangling，跨编译器兼容
- 无需链接任何 tyche 库（模块只需要打开 SHM 并写入）
- 接口声明 JSON 格式扩展性好

**建议补充**（向后兼容）：

```c
// 可选：模块版本声明（ABI 兼容性检查）
const char* tyche_module_version(void);  // 返回 "1.0" 等

// 可选：健康检查回调（引擎定期调用）
int tyche_module_health_check(void);     // 0=healthy, >0=error code
```

---

## 10. 结论

**该方案技术上完全可行，且已处于工程可用状态**。核心组件（DynamicLibrary、SharedMemoryQueue、SharedMemoryBridge）的实现质量很高，跨平台处理干净，性能设计面向低延迟。

主要的改进空间在**运维健壮性**（超时、崩溃恢复、残留清理）而非架构设计。建议按 P0→P1→P2 优先级逐步增强，不需要重构现有架构。

---

## 附录 A：相关文件清单

| 文件 | 说明 |
|------|------|
| `src/tyche/cpp/engine/module_interface.h` | 模块 C ABI 接口定义 |
| `src/tyche/cpp/engine/dynamic_library.h` | 跨平台动态库加载器 |
| `src/tyche/cpp/engine/dynamic_library.cpp` | Windows/Linux 双平台实现 |
| `src/tyche/cpp/engine/shared_memory_queue.h` | SPSC 共享内存队列 |
| `src/tyche/cpp/engine/shared_memory_queue.cpp` | 无锁 ring buffer 实现 |
| `src/tyche/cpp/engine/shared_memory_bridge.h` | SHM ↔ ZMQ 桥接管理器 |
| `src/tyche/cpp/engine/shared_memory_bridge.cpp` | 模块生命周期管理 |
| `tests/cpp/stubs/stub_shm_lib/stub_shm_lib.cpp` | 测试用 stub 模块 |
| `tests/cpp/stubs/stub_shm_lib/CMakeLists.txt` | Stub 模块构建配置 |
| `tests/cpp/test_shared_memory_bridge.cpp` | 集成测试 |
| `tests/perf/shm_bridge_bench.cpp` | 性能基准测试 |

---

## 附录 B：Stub 模块示例

```cpp
// tests/cpp/stubs/stub_shm_lib/stub_shm_lib.cpp
#include <cstring>
#include <iostream>
#include "tyche/cpp/engine/module_interface.h"

static char g_queue_name[256] = {0};
static bool g_running = false;

extern "C" {

int tyche_module_init(const char* shm_queue_name) {
    std::strncpy(g_queue_name, shm_queue_name, sizeof(g_queue_name) - 1);
    g_queue_name[sizeof(g_queue_name) - 1] = '\0';
    std::cerr << "[StubModule] init with queue: " << g_queue_name << std::endl;
    return 0;
}

int tyche_module_run(void) {
    std::cerr << "[StubModule] run started" << std::endl;
    std::cerr << "[StubModule] run exiting" << std::endl;
    return 0;
}

void tyche_module_stop(void) {
    g_running = false;
    std::cerr << "[StubModule] stop called" << std::endl;
}

const char* tyche_module_get_interfaces(void) {
    return R"([{"name":"on_test","pattern":"on","event_type":"test"}])";
}

} // extern "C"
```
