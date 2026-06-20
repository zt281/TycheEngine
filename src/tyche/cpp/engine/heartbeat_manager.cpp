#include "tyche/cpp/engine/heartbeat_manager.h"

#include <chrono>
#include <mutex>
#include <shared_mutex>

namespace tyche {

// ── Constructor ──────────────────────────────────────────────────────

HeartbeatManager::HeartbeatManager(double interval, int liveness)
    : _interval(interval), _liveness(liveness) {}

// ── Public methods ───────────────────────────────────────────────────

void HeartbeatManager::register_module(const std::string& module_id) {
    std::unique_lock lock(_mutex);
    // Grace period: liveness * 2, giving module extra time to establish connection
    _monitors.emplace(module_id, HeartbeatMonitor(_liveness * 2, now(), _interval));
}

void HeartbeatManager::update(const std::string& module_id) {
    std::unique_lock lock(_mutex);
    auto it = _monitors.find(module_id);
    if (it != _monitors.end()) {
        it->second.update(now(), _liveness);
    }
}

std::vector<std::string> HeartbeatManager::tick_all() {
    std::unique_lock lock(_mutex);
    std::vector<std::string> expired;

    for (auto& [mid, monitor] : _monitors) {
        monitor.tick();
        if (monitor.is_expired()) {
            expired.push_back(mid);
        }
    }

    // Remove expired monitors
    for (const auto& mid : expired) {
        _monitors.erase(mid);
    }

    return expired;
}

void HeartbeatManager::unregister(const std::string& module_id) {
    std::unique_lock lock(_mutex);
    _monitors.erase(module_id);
}

bool HeartbeatManager::is_registered(const std::string& module_id) const {
    std::shared_lock lock(_mutex);
    return _monitors.find(module_id) != _monitors.end();
}

size_t HeartbeatManager::size() const {
    std::shared_lock lock(_mutex);
    return _monitors.size();
}

int HeartbeatManager::get_liveness(const std::string& module_id) const {
    std::shared_lock lock(_mutex);
    auto it = _monitors.find(module_id);
    if (it != _monitors.end()) {
        return it->second.liveness;
    }
    return -1;
}

// ── Private helpers ──────────────────────────────────────────────────

double HeartbeatManager::now() {
    auto tp = std::chrono::system_clock::now();
    auto duration = tp.time_since_epoch();
    return std::chrono::duration<double>(duration).count();
}

}  // namespace tyche
