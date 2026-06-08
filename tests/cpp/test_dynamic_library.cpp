// Unit tests for tyche::DynamicLibrary - Cross-platform dynamic library loader.

#include <gtest/gtest.h>

#include "tyche/cpp/engine/dynamic_library.h"

namespace tyche {
namespace {

// ── Load non-existent library ─────────────────────────────────────────

TEST(DynamicLibraryTest, LoadNonExistentFails) {
    DynamicLibrary lib("nonexistent_library_xyz.dll");
    EXPECT_FALSE(lib.is_loaded());
}

TEST(DynamicLibraryTest, GetSymbolOnUnloadedReturnsNull) {
    DynamicLibrary lib("nonexistent_library_xyz.dll");
    EXPECT_EQ(lib.get_symbol("some_function"), nullptr);
}

TEST(DynamicLibraryTest, LastErrorOnFailure) {
    DynamicLibrary lib("nonexistent_library_xyz.dll");
    EXPECT_FALSE(lib.is_loaded());
    // Should have some error message
    std::string err = lib.last_error();
    EXPECT_FALSE(err.empty());
}

// ── Load self / system library ────────────────────────────────────────

TEST(DynamicLibraryTest, LoadSystemLibrary) {
#ifdef _WIN32
    // Try to load a common Windows DLL
    DynamicLibrary lib("kernel32.dll");
#else
    // Try to load libc
    DynamicLibrary lib("libc.so.6");
#endif
    // This may or may not succeed depending on the environment
    // We just verify the API works without crashing
    (void)lib.is_loaded();
    (void)lib.last_error();
}

TEST(DynamicLibraryTest, GetSymbolFromSystemLibrary) {
#ifdef _WIN32
    DynamicLibrary lib("kernel32.dll");
    if (lib.is_loaded()) {
        void* sym = lib.get_symbol("GetCurrentProcessId");
        EXPECT_NE(sym, nullptr);
    }
#else
    DynamicLibrary lib("libc.so.6");
    if (lib.is_loaded()) {
        void* sym = lib.get_symbol("malloc");
        EXPECT_NE(sym, nullptr);
    }
#endif
}

// ── Move semantics ────────────────────────────────────────────────────

TEST(DynamicLibraryTest, MoveConstruction) {
#ifdef _WIN32
    DynamicLibrary lib1("kernel32.dll");
#else
    DynamicLibrary lib1("libc.so.6");
#endif
    bool was_loaded = lib1.is_loaded();

    DynamicLibrary lib2(std::move(lib1));
    EXPECT_EQ(lib2.is_loaded(), was_loaded);
    EXPECT_FALSE(lib1.is_loaded());  // moved-from
}

}  // namespace
}  // namespace tyche
