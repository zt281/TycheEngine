#include "tyche/cpp/engine/shared_memory_queue.h"

#include <algorithm>
#include <cstring>

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace tyche {

// ── Platform-specific handles ───────────────────────────────────────

#ifdef _WIN32
struct SharedMemoryQueue::PlatformHandle {
    HANDLE hMapFile = nullptr;
};
#else
struct SharedMemoryQueue::PlatformHandle {
    int fd = -1;
};
#endif

// ── Layout helpers ──────────────────────────────────────────────────

size_t SharedMemoryQueue::_slot_stride() const {
    size_t slot_size = sizeof(SlotHeader) + _config.max_msg_size;
    // Align to 8 bytes
    return (slot_size + 7) & ~static_cast<size_t>(7);
}

size_t SharedMemoryQueue::_total_size() const {
    return sizeof(Header) + _config.slot_count * _slot_stride();
}

SharedMemoryQueue::SlotHeader* SharedMemoryQueue::slot_header(uint32_t index) const {
    if (!_mapped || index >= _config.slot_count) return nullptr;
    uint8_t* base = static_cast<uint8_t*>(_mapped) + sizeof(Header);
    return reinterpret_cast<SlotHeader*>(base + index * _slot_stride());
}

uint8_t* SharedMemoryQueue::slot_data(uint32_t index) const {
    if (!_mapped || index >= _config.slot_count) return nullptr;
    uint8_t* base = static_cast<uint8_t*>(_mapped) + sizeof(Header);
    return base + index * _slot_stride() + sizeof(SlotHeader);
}

// ── Constructor / Destructor ────────────────────────────────────────

SharedMemoryQueue::SharedMemoryQueue(const Config& config, bool owner)
    : _config(config), _owner(owner) {
    _mapped_size = _total_size();
    _handle = std::make_unique<PlatformHandle>();

#ifdef _WIN32
    // Windows: use the name directly (CreateFileMappingA/OpenFileMappingA)
    // Prefix to avoid collisions with other apps
    std::string full_name = "tyche_shm_" + config.name;

    if (owner) {
        _handle->hMapFile = CreateFileMappingA(
            INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0,
            static_cast<DWORD>(_mapped_size), full_name.c_str());
        if (!_handle->hMapFile) {
            if (GetLastError() == ERROR_ALREADY_EXISTS) {
                // Try to open existing
                _handle->hMapFile = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, full_name.c_str());
            }
            if (!_handle->hMapFile) return;
        }
    } else {
        _handle->hMapFile = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, full_name.c_str());
        if (!_handle->hMapFile) return;
    }

    _mapped = MapViewOfFile(_handle->hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, _mapped_size);
    if (!_mapped) return;

#else
    // Linux: shm_open with "/" prefix
    std::string shm_name = "/tyche_shm_" + config.name;

    if (owner) {
        // Remove any existing shm to ensure clean state
        shm_unlink(shm_name.c_str());

        _handle->fd = shm_open(shm_name.c_str(), O_CREAT | O_RDWR, 0666);
        if (_handle->fd < 0) return;

        if (ftruncate(_handle->fd, static_cast<off_t>(_mapped_size)) < 0) {
            close(_handle->fd);
            _handle->fd = -1;
            return;
        }
    } else {
        _handle->fd = shm_open(shm_name.c_str(), O_RDWR, 0666);
        if (_handle->fd < 0) return;
    }

    _mapped = mmap(nullptr, _mapped_size, PROT_READ | PROT_WRITE, MAP_SHARED, _handle->fd, 0);
    if (_mapped == MAP_FAILED) {
        _mapped = nullptr;
        return;
    }
#endif

    if (owner) {
        // Initialize header
        std::memset(_mapped, 0, _mapped_size);
        auto* h = header();
        h->slot_count = config.slot_count;
        h->max_msg_size = config.max_msg_size;
        h->magic = MAGIC;
        h->version = VERSION;
        h->write_seq.store(0, std::memory_order_relaxed);
        h->read_seq.store(0, std::memory_order_relaxed);

        // Initialize slot sequences
        for (uint32_t i = 0; i < config.slot_count; ++i) {
            auto* sh = slot_header(i);
            if (sh) {
                sh->sequence.store(i, std::memory_order_relaxed);
                sh->size = 0;
            }
        }
    } else {
        // Verify header
        auto* h = header();
        if (h->magic != MAGIC || h->version != VERSION) {
            return;
        }
        // Validate slot_count matches
        if (h->slot_count != config.slot_count || h->max_msg_size != config.max_msg_size) {
            return;
        }
    }

    _valid = true;
}

SharedMemoryQueue::~SharedMemoryQueue() {
    if (_mapped) {
#ifdef _WIN32
        UnmapViewOfFile(_mapped);
#else
        munmap(_mapped, _mapped_size);
#endif
        _mapped = nullptr;
    }

#ifdef _WIN32
    if (_handle && _handle->hMapFile) {
        CloseHandle(_handle->hMapFile);
        _handle->hMapFile = nullptr;
    }
#else
    if (_handle && _handle->fd >= 0) {
        close(_handle->fd);
        _handle->fd = -1;
    }
    if (_owner) {
        std::string shm_name = "/tyche_shm_" + _config.name;
        shm_unlink(shm_name.c_str());
    }
#endif
}

// ── Write ───────────────────────────────────────────────────────────

bool SharedMemoryQueue::write(const uint8_t* data, size_t size) {
    if (!_valid || size == 0 || size > _config.max_msg_size) return false;

    auto* h = header();
    uint32_t pos = h->write_seq.load(std::memory_order_relaxed);

    for (;;) {
        uint32_t idx = pos % h->slot_count;
        auto* sh = slot_header(idx);
        if (!sh) return false;

        uint32_t seq = sh->sequence.load(std::memory_order_acquire);
        int32_t diff = static_cast<int32_t>(seq) - static_cast<int32_t>(pos);

        if (diff == 0) {
            // Slot is available for writing
            if (h->write_seq.compare_exchange_weak(pos, pos + 1,
                    std::memory_order_relaxed, std::memory_order_relaxed)) {
                std::memcpy(slot_data(idx), data, size);
                sh->size = static_cast<uint32_t>(size);
                sh->sequence.store(pos + 1, std::memory_order_release);
                return true;
            }
            // CAS failed, pos updated, retry
        } else if (diff < 0) {
            // Queue is full
            return false;
        } else {
            // Another writer advanced (shouldn't happen in SPSC, but handle gracefully)
            pos = h->write_seq.load(std::memory_order_relaxed);
        }
    }
}

// ── Read ────────────────────────────────────────────────────────────

std::optional<std::vector<uint8_t>> SharedMemoryQueue::read() {
    if (!_valid) return std::nullopt;

    auto* h = header();
    uint32_t pos = h->read_seq.load(std::memory_order_relaxed);
    uint32_t idx = pos % h->slot_count;
    auto* sh = slot_header(idx);
    if (!sh) return std::nullopt;

    uint32_t seq = sh->sequence.load(std::memory_order_acquire);
    int32_t diff = static_cast<int32_t>(seq) - static_cast<int32_t>(pos + 1);

    if (diff == 0) {
        // Data is available
        uint32_t msg_size = sh->size;
        msg_size = (std::min)(msg_size, _config.max_msg_size);
        std::vector<uint8_t> result(msg_size);
        std::memcpy(result.data(), slot_data(idx), msg_size);

        // Mark slot as writable again: sequence = pos + slot_count + 1
        sh->sequence.store(pos + h->slot_count + 1, std::memory_order_release);
        h->read_seq.store(pos + 1, std::memory_order_relaxed);
        return result;
    }

    return std::nullopt;
}

// ── State queries ───────────────────────────────────────────────────

bool SharedMemoryQueue::empty() const {
    if (!_valid) return true;
    auto* h = header();
    uint32_t w = h->write_seq.load(std::memory_order_relaxed);
    uint32_t r = h->read_seq.load(std::memory_order_relaxed);
    return w == r;
}

size_t SharedMemoryQueue::size() const {
    if (!_valid) return 0;
    auto* h = header();
    uint32_t w = h->write_seq.load(std::memory_order_relaxed);
    uint32_t r = h->read_seq.load(std::memory_order_relaxed);
    return (w >= r) ? static_cast<size_t>(w - r) : 0;
}

size_t SharedMemoryQueue::capacity() const {
    return _config.slot_count;
}

} // namespace tyche
