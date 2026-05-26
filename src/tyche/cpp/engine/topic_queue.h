#pragma once

#include <atomic>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "tyche/cpp/types.h"
#include "tyche/cpp/engine/ring_buffer.h"

namespace tyche {

/// 队列中的单个条目：入队时间 + ZMQ 多帧消息
struct QueueItem {
    double enqueue_time = 0.0;                 // epoch seconds
    std::vector<std::vector<uint8_t>> frames;  // ZMQ 多帧消息

    QueueItem() = default;
    QueueItem(double t, std::vector<std::vector<uint8_t>> f)
        : enqueue_time(t), frames(std::move(f)) {}
};

/// 主题队列 - 封装 RingBuffer，添加背压策略和统计
///
/// 每个事件主题（如 "tick", "quote"）对应一个 TopicQueue 实例。
/// Engine 的 event_proxy_worker 向队列写入，event_egress_worker 从队列读取。
class TopicQueue {
public:
    /// 构造函数
    /// @param capacity 队列容量，默认 10000
    /// @param strategy 背压策略，默认 DROP_OLDEST
    explicit TopicQueue(
        size_t capacity = 10000,
        BackpressureStrategy strategy = BackpressureStrategy::DROP_OLDEST);

    /// 放入一个条目，根据背压策略处理满队列情况
    /// @return true 如果成功入队，false 如果被丢弃（DROP_NEWEST）
    bool put(QueueItem item);

    /// 取出一个条目
    /// @return 条目，或 nullopt 如果队列为空
    std::optional<QueueItem> get();

    /// 当前队列大小（近似值）
    size_t size() const noexcept;

    /// 队列是否为空
    bool empty() const noexcept;

    /// 队列容量
    size_t capacity() const noexcept;

    /// 已处理的条目数
    uint64_t processed() const noexcept { return _processed.load(std::memory_order_relaxed); }

    /// 已丢弃的条目数
    uint64_t dropped() const noexcept { return _dropped.load(std::memory_order_relaxed); }

    /// 获取背压策略
    BackpressureStrategy strategy() const noexcept { return _strategy; }

private:
    RingBuffer<QueueItem> _buffer;
    BackpressureStrategy _strategy;
    std::atomic<uint64_t> _processed{0};
    std::atomic<uint64_t> _dropped{0};
};

}  // namespace tyche
