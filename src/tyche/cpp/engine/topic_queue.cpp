#include "tyche/cpp/engine/topic_queue.h"

namespace tyche {

TopicQueue::TopicQueue(size_t capacity, BackpressureStrategy strategy)
    : _buffer(capacity), _strategy(strategy) {}

bool TopicQueue::put(QueueItem item) {
    switch (_strategy) {
        case BackpressureStrategy::DROP_OLDEST:
            _buffer.push_overwrite(std::move(item));
            return true;

        case BackpressureStrategy::DROP_NEWEST:
            if (_buffer.try_push(std::move(item))) {
                return true;
            }
            _dropped.fetch_add(1, std::memory_order_relaxed);
            return false;

        case BackpressureStrategy::BLOCK_PRODUCER:
            _buffer.push_blocking(std::move(item));
            return true;
    }
    // Fallback: try_push
    return _buffer.try_push(std::move(item));
}

std::optional<QueueItem> TopicQueue::get() {
    auto item = _buffer.pop();
    if (item.has_value()) {
        _processed.fetch_add(1, std::memory_order_relaxed);
    }
    return item;
}

size_t TopicQueue::size() const noexcept {
    return _buffer.size();
}

bool TopicQueue::empty() const noexcept {
    return _buffer.empty();
}

size_t TopicQueue::capacity() const noexcept {
    return _buffer.capacity();
}

}  // namespace tyche
