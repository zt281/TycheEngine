#pragma once

#include <memory>
#include <string>

namespace tyche {

// Cross-platform dynamic library loader.
// RAII wrapper around LoadLibrary / dlopen.

class DynamicLibrary {
public:
    explicit DynamicLibrary(const std::string& path);
    ~DynamicLibrary();

    DynamicLibrary(const DynamicLibrary&) = delete;
    DynamicLibrary& operator=(const DynamicLibrary&) = delete;

    DynamicLibrary(DynamicLibrary&& other) noexcept;
    DynamicLibrary& operator=(DynamicLibrary&& other) noexcept;

    bool is_loaded() const;

    // Get a symbol from the library.
    // Returns nullptr if not found or library not loaded.
    void* get_symbol(const std::string& name) const;

    // Typed accessor for function pointers.
    template <typename T>
    T* get_function(const std::string& name) const {
        return reinterpret_cast<T*>(get_symbol(name));
    }

    const std::string& path() const { return _path; }

    // Get last error message from the OS loader.
    std::string last_error() const;

private:
    struct Impl;
    std::unique_ptr<Impl> _impl;
    std::string _path;
    bool _loaded = false;
};

} // namespace tyche
