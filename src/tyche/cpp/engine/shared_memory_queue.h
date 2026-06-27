#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace tyche {

// Cross-platform shared memory queue for inter-process communication.
//
// Uses a ring buffer of fixed-size slots with sequence-number synchronization.
// Thread-safe for single-producer + single-consumer (SPSC).
// Both ends may be in different processes.
//
// Layout in shared memory:
//   [Header (64 bytes)]
//   [Slot 0: sequence(4) + size(4) + data[max_msg_size]]
//   [Slot 1: ...]
//   ...
//
// Windows: uses CreateFileMapping / MapViewOfFile
// Linux:   uses shm_open / mmap

class SharedMemoryQueue {
public:
    struct Config {
        std::string name;              // shared memory object name
        uint32_t slot_count = 2048;    // number of slots
        uint32_t max_msg_size = 4096;  // maximum message size per slot
    };

    // Create (owner=true) or open (owner=false) a shared memory queue.
    // Owner creates and destroys the shared memory segment.
    SharedMemoryQueue(const Config& config, bool owner = false);
    ~SharedMemoryQueue();

    SharedMemoryQueue(const SharedMemoryQueue&) = delete;
    SharedMemoryQueue& operator=(const SharedMemoryQueue&) = delete;

    // Write a message. Returns false if queue is full or message too large.
    bool write(const uint8_t* data, size_t size);
    bool write(const std::vector<uint8_t>& data) {
        return write(data.data(), data.size());
    }

    // Read a message. Returns empty optional if queue is empty.
    std::optional<std::vector<uint8_t>> read();

    /// Zero-allocation read: copies message into caller-provided buffer.
    /// Returns true if a message was read, false if queue is empty.
    /// out_size is set to the actual message size on success.
    /// If buffer_size < message size, the message is truncated and out_size
    /// reflects the actual (untruncated) size.
    bool read_into(uint8_t* buffer, size_t buffer_size, size_t& out_size);

    bool empty() const;
    size_t size() const;
    size_t capacity() const;

    bool is_valid() const { return _valid; }
    const std::string& name() const { return _config.name; }

    /// Clean up stale shared memory segments from previous crashed processes.
    /// On Linux: scans /dev/shm/tyche_shm_* and unlinks them.
    /// On Windows: no-op (kernel reference counting handles cleanup).
    static void cleanup_stale();

private:
    static constexpr uint32_t MAGIC = 0x54594843;  // 'TYCH'
    static constexpr uint32_t VERSION = 1;

    struct PlatformHandle;
    std::unique_ptr<PlatformHandle> _handle;

    Config _config;
    bool _owner;
    bool _valid = false;

    void* _mapped = nullptr;
    size_t _mapped_size = 0;

#pragma pack(push, 1)
    struct Header {
        std::atomic<uint32_t> write_seq;
        uint32_t _pad0;
        std::atomic<uint32_t> read_seq;
        uint32_t _pad1;
        uint32_t slot_count;
        uint32_t max_msg_size;
        uint32_t magic;
        uint32_t version;
        uint32_t reserved[8];
    };
#pragma pack(pop)

    static_assert(sizeof(Header) == 64, "Header must be exactly 64 bytes");

    Header* header() const {
        return static_cast<Header*>(_mapped);
    }

    struct SlotHeader {
        std::atomic<uint32_t> sequence;
        uint32_t size;
    };

    uint8_t* slot_data(uint32_t index) const;
    SlotHeader* slot_header(uint32_t index) const;

    size_t _slot_stride() const;
    size_t _total_size() const;
};

} // namespace tyche
