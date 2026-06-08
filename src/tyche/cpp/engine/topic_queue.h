#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "tyche/cpp/types.h"
#include "tyche/cpp/engine/ring_buffer.h"

namespace tyche {

// ── Small-Buffer-Optimized Frame ──────────────────────────────────────
//
// OPT-1: Eliminates per-frame heap allocation for small messages.
// Frames <= SSO_SIZE are stored inline; larger frames use a single
// heap allocation. This removes the vector-of-vector overhead from
// the original std::vector<std::vector<uint8_t>> design.

class Frame {
public:
    static constexpr size_t SSO_SIZE = 64;

    Frame() = default;

    // Construct from raw bytes (zero-copy for small frames via inline storage)
    explicit Frame(const uint8_t* data, size_t len) {
        if (len <= SSO_SIZE) {
            _size = static_cast<uint8_t>(len);
            if (len > 0) std::memcpy(_sso_buf, data, len);
        } else {
            _size = 0xFF;  // marker: heap allocated
            _heap_len = len;
            _heap_ptr = std::make_unique<uint8_t[]>(len);
            std::memcpy(_heap_ptr.get(), data, len);
        }
    }

    // Construct from zmq::message_t without intermediate to_bytes()
    template <typename T>
    explicit Frame(const T& zmq_msg)
        : Frame(static_cast<const uint8_t*>(zmq_msg.data()), zmq_msg.size()) {}

    // Copy constructor
    Frame(const Frame& other)
        : _size(other._size), _heap_len(other._heap_len) {
        if (_size == 0xFF) {
            _heap_ptr = std::make_unique<uint8_t[]>(_heap_len);
            std::memcpy(_heap_ptr.get(), other._heap_ptr.get(), _heap_len);
        } else {
            std::memcpy(_sso_buf, other._sso_buf, _size);
        }
    }

    Frame& operator=(const Frame& other) {
        if (this != &other) {
            _size = other._size;
            _heap_len = other._heap_len;
            if (_size == 0xFF) {
                _heap_ptr = std::make_unique<uint8_t[]>(_heap_len);
                std::memcpy(_heap_ptr.get(), other._heap_ptr.get(), _heap_len);
            } else {
                std::memcpy(_sso_buf, other._sso_buf, _size);
            }
        }
        return *this;
    }

    // Move constructor
    Frame(Frame&& other) noexcept
        : _size(other._size), _heap_len(other._heap_len) {
        if (_size == 0xFF) {
            _heap_ptr = std::move(other._heap_ptr);
        } else {
            std::memcpy(_sso_buf, other._sso_buf, _size);
        }
        other._size = 0;
        other._heap_len = 0;
    }

    // Move assignment
    Frame& operator=(Frame&& other) noexcept {
        if (this != &other) {
            _size = other._size;
            _heap_len = other._heap_len;
            if (_size == 0xFF) {
                _heap_ptr = std::move(other._heap_ptr);
            } else {
                std::memcpy(_sso_buf, other._sso_buf, _size);
            }
            other._size = 0;
            other._heap_len = 0;
        }
        return *this;
    }

    const uint8_t* data() const noexcept {
        return (_size == 0xFF) ? _heap_ptr.get() : _sso_buf;
    }

    size_t size() const noexcept {
        return (_size == 0xFF) ? _heap_len : _size;
    }

    bool empty() const noexcept { return size() == 0; }

    // Convert to std::vector<uint8_t> for compatibility with existing code
    std::vector<uint8_t> to_vector() const {
        const uint8_t* p = data();
        size_t n = size();
        return {p, p + n};
    }

    // Equality comparison without conversion
    bool operator==(const Frame& other) const noexcept {
        size_t n = size();
        if (n != other.size()) return false;
        return std::memcmp(data(), other.data(), n) == 0;
    }

    bool operator!=(const Frame& other) const noexcept { return !(*this == other); }

private:
    uint8_t _size = 0;            // 0xFF means heap-allocated, else inline size
    uint8_t _sso_buf[SSO_SIZE] = {};
    std::unique_ptr<uint8_t[]> _heap_ptr;
    size_t _heap_len = 0;
};

/// 队列中的单个条目：入队时间 + ZMQ 多帧消息
struct QueueItem {
    double enqueue_time = 0.0;    // epoch seconds
    std::vector<Frame> frames;    // ZMQ 多帧消息 (SSO-optimized)

    QueueItem() = default;
    QueueItem(double t, std::vector<Frame> f)
        : enqueue_time(t), frames(std::move(f)) {}

    // Backward-compatible constructor from vector-of-vector
    QueueItem(double t, std::vector<std::vector<uint8_t>> f)
        : enqueue_time(t) {
        frames.reserve(f.size());
        for (auto& v : f) {
            frames.emplace_back(v.data(), v.size());
        }
    }
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
