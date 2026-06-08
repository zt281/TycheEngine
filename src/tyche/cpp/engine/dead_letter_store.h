#pragma once

#include <mutex>
#include <optional>
#include <string>
#include <vector>
#include <any>
#include <unordered_map>

namespace tyche {

// Forward declare to avoid circular include
struct Message;

/// 死信存储 - 按日期分文件的 JSONL 持久化
///
/// 线程安全：所有写操作使用 mutex 保护。
/// 异常安全：persist() 不抛出异常，仅记日志。
class DeadLetterStore {
public:
    /// 构造函数
    /// @param data_dir 死信文件存储目录，默认 "data/dead_letters"
    explicit DeadLetterStore(const std::string& data_dir = "data/dead_letters");

    /// 持久化一条死信记录
    /// @param msg 原始消息
    /// @param topic 消息主题
    /// @param reason 死信原因: "broadcast_ttl_expired", "wait_timeout", "run_timeout"
    void persist(const Message& msg, const std::string& topic, const std::string& reason);

    /// 查询死信记录
    /// @param topic_filter 可选主题过滤
    /// @param since_date 可选起始日期 (格式: "YYYY-MM-DD")
    /// @param max_count 最大返回条数，默认 100
    /// @return JSONL 格式的记录列表（每个元素是一行 JSON）
    std::vector<std::string> replay(
        const std::optional<std::string>& topic_filter = std::nullopt,
        const std::optional<std::string>& since_date = std::nullopt,
        size_t max_count = 100) const;

    /// 获取数据目录路径
    const std::string& data_dir() const { return _data_dir; }

private:
    std::string _data_dir;
    mutable std::mutex _write_lock;

    /// 获取今天的日期字符串 "YYYY-MM-DD"
    static std::string today_str();

    /// 将 Message 序列化为 JSON 字符串
    static std::string message_to_json(const Message& msg);

    /// 将 Payload (std::any map) 序列化为 JSON
    static std::string payload_to_json(const std::unordered_map<std::string, std::any>& payload);

    /// 转义 JSON 字符串中的特殊字符
    static std::string escape_json_string(const std::string& s);

    /// 将 std::any 值序列化为 JSON
    static std::string any_to_json(const std::any& value);

    /// 确保目录存在
    static bool ensure_directory(const std::string& path);
};

}  // namespace tyche
