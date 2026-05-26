#pragma once

#include <chrono>
#include <shared_mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace tyche {

// 常量（与 Python types.py 一致）
inline constexpr double HEARTBEAT_INTERVAL_SEC = 1.0;
inline constexpr int HEARTBEAT_LIVENESS_DEFAULT = 3;

/// 单个模块的心跳监控状态
struct HeartbeatMonitor {
    int liveness;          // 剩余存活计数，<=0 则过期
    double last_seen;      // 最后一次收到心跳的时间 (epoch seconds)
    double interval;       // 心跳间隔 (seconds)

    HeartbeatMonitor() : liveness(0), last_seen(0.0), interval(HEARTBEAT_INTERVAL_SEC) {}
    HeartbeatMonitor(int initial_liveness, double now, double ivl = HEARTBEAT_INTERVAL_SEC)
        : liveness(initial_liveness), last_seen(now), interval(ivl) {}

    /// 每个 tick 周期调用一次，递减 liveness
    void tick() { --liveness; }

    /// 收到心跳时调用，重置 liveness
    void update(double now, int reset_liveness = HEARTBEAT_LIVENESS_DEFAULT) {
        liveness = reset_liveness;
        last_seen = now;
    }

    /// 是否已过期
    bool is_expired() const { return liveness <= 0; }
};

/// 心跳管理器 - Paranoid Pirate Pattern
///
/// 管理所有已注册模块的心跳状态。
/// 线程安全：使用 shared_mutex 支持并发读取。
class HeartbeatManager {
public:
    explicit HeartbeatManager(
        double interval = HEARTBEAT_INTERVAL_SEC,
        int liveness = HEARTBEAT_LIVENESS_DEFAULT);

    /// 注册模块，初始 liveness = _liveness * 2 (grace period)
    void register_module(const std::string& module_id);

    /// 收到心跳时更新，重置 liveness = _liveness
    void update(const std::string& module_id);

    /// 每个 tick 周期调用一次，返回已过期的 module_id 列表
    std::vector<std::string> tick_all();

    /// 注销模块
    void unregister(const std::string& module_id);

    /// 检查模块是否已注册
    bool is_registered(const std::string& module_id) const;

    /// 获取监控数量
    size_t size() const;

    /// 获取指定模块的 liveness（用于调试/查询），-1 表示未找到
    int get_liveness(const std::string& module_id) const;

private:
    double _interval;
    int _liveness;
    mutable std::shared_mutex _mutex;
    std::unordered_map<std::string, HeartbeatMonitor> _monitors;

    /// 获取当前时间 (epoch seconds)
    static double now();
};

}  // namespace tyche
