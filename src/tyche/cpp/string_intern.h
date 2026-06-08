#pragma once

// Fast string interning for topic and module IDs.
//
// OPT-3: Maps strings to dense uint32_t IDs at registration time.
// All internal lookups (arrays, flat_hash_map, etc.) use the uint32_t ID
// instead of std::string, eliminating repeated hashing and string comparisons
// on hot paths.
//
// Thread-safe: multiple threads may intern strings concurrently.
// ID 0 is reserved for "invalid / not found".

#include <atomic>
#include <cstdint>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace tyche {

using InternId = uint32_t;

inline constexpr InternId INVALID_INTERN_ID = 0;

class StringIntern {
public:
    StringIntern() = default;

    // Map a string to its interned ID. If the string has not been seen before,
    // assigns a new ID. Otherwise returns the existing ID.
    // Thread-safe.
    InternId intern(std::string_view sv) {
        // Fast path: read-only lookup under shared lock
        // NOTE: MSVC C++17 unordered_map does not support heterogeneous lookup
        // with string_view; we construct a temporary std::string.
        {
            std::shared_lock lock(_mutex);
            auto it = _string_to_id.find(std::string(sv));
            if (it != _string_to_id.end()) {
                return it->second;
            }
        }

        // Slow path: insert under exclusive lock
        std::unique_lock lock(_mutex);
        auto it = _string_to_id.find(std::string(sv));
        if (it != _string_to_id.end()) {
            return it->second;
        }

        InternId id = _next_id.fetch_add(1, std::memory_order_relaxed);
        std::string owned(sv);
        _string_to_id[owned] = id;
        if (id >= _id_to_string.size()) {
            _id_to_string.resize(id + 1);
        }
        _id_to_string[id] = std::move(owned);
        return id;
    }

    // Lookup existing interned ID without creating a new one.
    // Returns INVALID_INTERN_ID if not found.
    // Thread-safe.
    InternId lookup(std::string_view sv) const {
        std::shared_lock lock(_mutex);
        auto it = _string_to_id.find(std::string(sv));
        if (it != _string_to_id.end()) {
            return it->second;
        }
        return INVALID_INTERN_ID;
    }

    // Reverse lookup: get the original string for an ID.
    // Returns empty string_view if ID is invalid.
    // Thread-safe.
    std::string_view resolve(InternId id) const {
        std::shared_lock lock(_mutex);
        if (id < _id_to_string.size()) {
            return _id_to_string[id];
        }
        return {};
    }

    // Number of interned strings.
    size_t size() const {
        std::shared_lock lock(_mutex);
        return _string_to_id.size();
    }

private:
    mutable std::shared_mutex _mutex;
    std::unordered_map<std::string, InternId> _string_to_id;
    std::vector<std::string> _id_to_string;
    std::atomic<InternId> _next_id{1};  // ID 0 reserved for invalid
};

}  // namespace tyche
