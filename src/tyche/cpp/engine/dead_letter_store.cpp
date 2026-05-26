#include "tyche/cpp/engine/dead_letter_store.h"
#include "tyche/cpp/message.h"
#include "tyche/cpp/types.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace tyche {

// ── Constructor ──────────────────────────────────────────────────────

DeadLetterStore::DeadLetterStore(const std::string& data_dir)
    : _data_dir(data_dir) {}

// ── persist() ────────────────────────────────────────────────────────

void DeadLetterStore::persist(const Message& msg, const std::string& topic, const std::string& reason) {
    try {
        std::string date = today_str();
        std::string filepath = _data_dir + "/" + date + ".jsonl";

        // Current timestamp as epoch seconds with fractional part
        auto now = std::chrono::system_clock::now();
        auto epoch = now.time_since_epoch();
        double timestamp = std::chrono::duration<double>(epoch).count();

        // Build JSON record
        std::ostringstream oss;
        oss << std::setprecision(17);
        oss << "{\"timestamp\": " << timestamp
            << ", \"topic\": \"" << escape_json_string(topic)
            << "\", \"reason\": \"" << escape_json_string(reason)
            << "\", \"message\": " << message_to_json(msg) << "}";

        std::string record = oss.str() + "\n";

        std::lock_guard<std::mutex> lock(_write_lock);
        ensure_directory(_data_dir);

        std::ofstream file(filepath, std::ios::app | std::ios::binary);
        if (file.is_open()) {
            file << record;
        } else {
            std::cerr << "[DeadLetterStore] Cannot open file: " << filepath << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "[DeadLetterStore] Failed to persist dead letter: " << e.what() << std::endl;
    } catch (...) {
        std::cerr << "[DeadLetterStore] Failed to persist dead letter (unknown error)" << std::endl;
    }
}

// ── replay() ─────────────────────────────────────────────────────────

std::vector<std::string> DeadLetterStore::replay(
    const std::optional<std::string>& topic_filter,
    const std::optional<std::string>& since_date,
    size_t max_count) const {

    std::vector<std::string> results;
    namespace fs = std::filesystem;

    if (!fs::exists(_data_dir) || !fs::is_directory(_data_dir)) {
        return results;
    }

    // Collect and sort .jsonl files
    std::vector<fs::path> files;
    try {
        for (const auto& entry : fs::directory_iterator(_data_dir)) {
            if (entry.is_regular_file() && entry.path().extension() == ".jsonl") {
                files.push_back(entry.path());
            }
        }
    } catch (...) {
        std::cerr << "[DeadLetterStore] Failed to list dead letter files" << std::endl;
        return results;
    }

    std::sort(files.begin(), files.end());

    for (const auto& file_path : files) {
        if (results.size() >= max_count) {
            break;
        }

        // Extract date from filename (stem = "YYYY-MM-DD")
        std::string file_date = file_path.stem().string();

        // Filter by since_date
        if (since_date.has_value() && file_date < since_date.value()) {
            continue;
        }

        // Read file line by line
        std::ifstream file(file_path, std::ios::in);
        if (!file.is_open()) {
            continue;
        }

        std::string line;
        while (std::getline(file, line) && results.size() < max_count) {
            // Trim whitespace
            if (line.empty()) {
                continue;
            }

            // Filter by topic if specified
            if (topic_filter.has_value()) {
                // Simple substring check: look for "topic": "value"
                std::string needle = "\"topic\": \"" + topic_filter.value() + "\"";
                std::string needle_compact = "\"topic\":\"" + topic_filter.value() + "\"";
                if (line.find(needle) == std::string::npos &&
                    line.find(needle_compact) == std::string::npos) {
                    continue;
                }
            }

            results.push_back(line);
        }
    }

    return results;
}

// ── today_str() ──────────────────────────────────────────────────────

std::string DeadLetterStore::today_str() {
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buf{};
#ifdef _WIN32
    localtime_s(&tm_buf, &time);
#else
    localtime_r(&time, &tm_buf);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d");
    return oss.str();
}

// ── message_to_json() ────────────────────────────────────────────────

std::string DeadLetterStore::message_to_json(const Message& msg) {
    std::ostringstream oss;
    oss << std::setprecision(17);

    oss << "{\"msg_type\": \"" << message_type_to_str(msg.msg_type) << "\"";
    oss << ", \"sender\": \"" << escape_json_string(msg.sender) << "\"";
    oss << ", \"event\": \"" << escape_json_string(msg.event) << "\"";
    oss << ", \"payload\": " << payload_to_json(msg.payload);

    // recipient (nullable)
    if (msg.recipient.has_value()) {
        oss << ", \"recipient\": \"" << escape_json_string(msg.recipient.value()) << "\"";
    } else {
        oss << ", \"recipient\": null";
    }

    // durability as integer
    oss << ", \"durability\": " << static_cast<int>(msg.durability);

    // timestamp (nullable)
    if (msg.timestamp.has_value()) {
        oss << ", \"timestamp\": " << msg.timestamp.value();
    } else {
        oss << ", \"timestamp\": null";
    }

    // correlation_id (nullable)
    if (msg.correlation_id.has_value()) {
        oss << ", \"correlation_id\": \"" << escape_json_string(msg.correlation_id.value()) << "\"";
    } else {
        oss << ", \"correlation_id\": null";
    }

    // wait_timeout (nullable)
    if (msg.wait_timeout.has_value()) {
        oss << ", \"wait_timeout\": " << msg.wait_timeout.value();
    } else {
        oss << ", \"wait_timeout\": null";
    }

    // run_timeout (nullable)
    if (msg.run_timeout.has_value()) {
        oss << ", \"run_timeout\": " << msg.run_timeout.value();
    } else {
        oss << ", \"run_timeout\": null";
    }

    oss << "}";
    return oss.str();
}

// ── payload_to_json() ────────────────────────────────────────────────

std::string DeadLetterStore::payload_to_json(const std::unordered_map<std::string, std::any>& payload) {
    if (payload.empty()) {
        return "{}";
    }

    std::ostringstream oss;
    oss << std::setprecision(17);
    oss << "{";

    bool first = true;
    for (const auto& [key, value] : payload) {
        if (!first) {
            oss << ", ";
        }
        first = false;
        oss << "\"" << escape_json_string(key) << "\": " << any_to_json(value);
    }

    oss << "}";
    return oss.str();
}

// ── any_to_json() ────────────────────────────────────────────────────

std::string DeadLetterStore::any_to_json(const std::any& value) {
    if (!value.has_value()) {
        return "null";
    }

    // String types
    if (value.type() == typeid(std::string)) {
        return "\"" + escape_json_string(std::any_cast<std::string>(value)) + "\"";
    }
    if (value.type() == typeid(const char*)) {
        return "\"" + escape_json_string(std::any_cast<const char*>(value)) + "\"";
    }

    // Boolean (must check before int since bool can implicitly convert)
    if (value.type() == typeid(bool)) {
        return std::any_cast<bool>(value) ? "true" : "false";
    }

    // Integer types
    if (value.type() == typeid(int)) {
        return std::to_string(std::any_cast<int>(value));
    }
    if (value.type() == typeid(int64_t)) {
        return std::to_string(std::any_cast<int64_t>(value));
    }
    if (value.type() == typeid(uint64_t)) {
        return std::to_string(std::any_cast<uint64_t>(value));
    }
    if (value.type() == typeid(unsigned int)) {
        return std::to_string(std::any_cast<unsigned int>(value));
    }
    if (value.type() == typeid(long)) {
        return std::to_string(std::any_cast<long>(value));
    }
    if (value.type() == typeid(unsigned long)) {
        return std::to_string(std::any_cast<unsigned long>(value));
    }

    // Floating point types (handle NaN/Inf)
    if (value.type() == typeid(double)) {
        double d = std::any_cast<double>(value);
        if (std::isnan(d) || std::isinf(d)) {
            return "null";
        }
        std::ostringstream oss;
        oss << std::setprecision(17) << d;
        std::string s = oss.str();
        // Ensure it looks like a float (has decimal point or exponent)
        if (s.find('.') == std::string::npos && s.find('e') == std::string::npos) {
            s += ".0";
        }
        return s;
    }
    if (value.type() == typeid(float)) {
        float f = std::any_cast<float>(value);
        if (std::isnan(f) || std::isinf(f)) {
            return "null";
        }
        std::ostringstream oss;
        oss << std::setprecision(9) << f;
        std::string s = oss.str();
        if (s.find('.') == std::string::npos && s.find('e') == std::string::npos) {
            s += ".0";
        }
        return s;
    }

    // Nested Payload (map)
    if (value.type() == typeid(Payload)) {
        return payload_to_json(std::any_cast<Payload>(value));
    }
    if (value.type() == typeid(std::unordered_map<std::string, std::any>)) {
        return payload_to_json(std::any_cast<std::unordered_map<std::string, std::any>>(value));
    }

    // Vector of std::any
    if (value.type() == typeid(std::vector<std::any>)) {
        const auto& vec = std::any_cast<std::vector<std::any>>(value);
        std::ostringstream oss;
        oss << "[";
        for (size_t i = 0; i < vec.size(); ++i) {
            if (i > 0) oss << ", ";
            oss << any_to_json(vec[i]);
        }
        oss << "]";
        return oss.str();
    }

    // Fallback: unknown type -> null
    return "null";
}

// ── escape_json_string() ─────────────────────────────────────────────

std::string DeadLetterStore::escape_json_string(const std::string& s) {
    std::string result;
    result.reserve(s.size() + 16);

    for (char c : s) {
        switch (c) {
            case '"':  result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\n': result += "\\n";  break;
            case '\r': result += "\\r";  break;
            case '\t': result += "\\t";  break;
            case '\b': result += "\\b";  break;
            case '\f': result += "\\f";  break;
            default:
                // Escape control characters (0x00-0x1F)
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned char>(c));
                    result += buf;
                } else {
                    result += c;
                }
                break;
        }
    }

    return result;
}

// ── ensure_directory() ───────────────────────────────────────────────

bool DeadLetterStore::ensure_directory(const std::string& path) {
    namespace fs = std::filesystem;
    try {
        fs::create_directories(path);
        return true;
    } catch (...) {
        return false;
    }
}

}  // namespace tyche
