#include "tyche/cpp/engine/dynamic_library.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

#include <cstring>

namespace tyche {

#ifdef _WIN32
struct DynamicLibrary::Impl {
    HMODULE handle = nullptr;
};
#else
struct DynamicLibrary::Impl {
    void* handle = nullptr;
};
#endif

DynamicLibrary::DynamicLibrary(const std::string& path)
    : _path(path), _impl(std::make_unique<Impl>()) {
#ifdef _WIN32
    _impl->handle = LoadLibraryA(path.c_str());
    _loaded = (_impl->handle != nullptr);
#else
    _impl->handle = dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    _loaded = (_impl->handle != nullptr);
#endif
}

DynamicLibrary::~DynamicLibrary() {
    if (_impl) {
#ifdef _WIN32
        if (_impl->handle) FreeLibrary(_impl->handle);
#else
        if (_impl->handle) dlclose(_impl->handle);
#endif
    }
}

DynamicLibrary::DynamicLibrary(DynamicLibrary&& other) noexcept
    : _impl(std::move(other._impl))
    , _path(std::move(other._path))
    , _loaded(other._loaded) {
    other._loaded = false;
}

DynamicLibrary& DynamicLibrary::operator=(DynamicLibrary&& other) noexcept {
    if (this != &other) {
        _impl = std::move(other._impl);
        _path = std::move(other._path);
        _loaded = other._loaded;
        other._loaded = false;
    }
    return *this;
}

bool DynamicLibrary::is_loaded() const {
    return _loaded;
}

void* DynamicLibrary::get_symbol(const std::string& name) const {
    if (!_loaded) return nullptr;
#ifdef _WIN32
    return reinterpret_cast<void*>(GetProcAddress(_impl->handle, name.c_str()));
#else
    return dlsym(_impl->handle, name.c_str());
#endif
}

std::string DynamicLibrary::last_error() const {
#ifdef _WIN32
    DWORD err = GetLastError();
    if (err == 0) return "";
    LPSTR msg_buf = nullptr;
    size_t size = FormatMessageA(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr, err, MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
        reinterpret_cast<LPSTR>(&msg_buf), 0, nullptr);
    std::string result;
    if (msg_buf && size > 0) {
        result.assign(msg_buf, size);
    }
    if (msg_buf) LocalFree(msg_buf);
    // Trim trailing newline
    while (!result.empty() && (result.back() == '\n' || result.back() == '\r')) {
        result.pop_back();
    }
    return result;
#else
    const char* err = dlerror();
    return err ? std::string(err) : "";
#endif
}

} // namespace tyche
