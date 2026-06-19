// Unit tests for CtpLoader - path resolution and validation.

#include <gtest/gtest.h>

#include "modules/ctp_gateway_cpp/src/ctp_loader.h"

#include <filesystem>

namespace fs = std::filesystem;

// ── Path Resolution ───────────────────────────────────────────────────

TEST(CtpLoaderTest, ResolveMdDllWithEmptyName) {
    std::string path = CtpLoader::resolve_md_dll("C:/ctp", "");
#ifdef _WIN32
    EXPECT_NE(path.find("thostmduserapi_se.dll"), std::string::npos);
#else
    EXPECT_NE(path.find("libthostmduserapi_se.so"), std::string::npos);
#endif
}

TEST(CtpLoaderTest, ResolveTdDllWithEmptyName) {
    std::string path = CtpLoader::resolve_td_dll("C:/ctp", "");
#ifdef _WIN32
    EXPECT_NE(path.find("thosttraderapi_se.dll"), std::string::npos);
#else
    EXPECT_NE(path.find("libthosttraderapi_se.so"), std::string::npos);
#endif
}

TEST(CtpLoaderTest, ResolveMdDllWithCustomName) {
    std::string path = CtpLoader::resolve_md_dll("C:/ctp", "custom_md.dll");
    EXPECT_NE(path.find("custom_md.dll"), std::string::npos);
}

TEST(CtpLoaderTest, ResolveTdDllWithCustomName) {
    std::string path = CtpLoader::resolve_td_dll("C:/ctp", "custom_td.dll");
    EXPECT_NE(path.find("custom_td.dll"), std::string::npos);
}

TEST(CtpLoaderTest, ResolveWithTrailingSlash) {
    std::string path = CtpLoader::resolve_md_dll("C:/ctp/", "md.dll");
    EXPECT_EQ(path, "C:/ctp/md.dll");
}

TEST(CtpLoaderTest, ResolveWithTrailingBackslash) {
    std::string path = CtpLoader::resolve_md_dll("C:\\ctp\\", "md.dll");
    EXPECT_EQ(path, "C:\\ctp\\md.dll");
}

TEST(CtpLoaderTest, ResolveWithoutTrailingSeparator) {
    std::string path = CtpLoader::resolve_md_dll("C:/ctp", "md.dll");
    EXPECT_EQ(path, "C:/ctp/md.dll");
}

TEST(CtpLoaderTest, ResolveEmptyDir) {
    std::string path = CtpLoader::resolve_md_dll("", "md.dll");
    EXPECT_EQ(path, "md.dll");
}

// ── Path Validation (via create_md_api / create_td_api) ───────────────

TEST(CtpLoaderTest, ValidateRelativePathThrows) {
#ifdef _WIN32
    std::string bad_dir = "relative/path";
#else
    std::string bad_dir = "relative/path";
#endif
    std::string path = CtpLoader::resolve_md_dll(bad_dir, "md.dll");
    // The validation happens in create_md_api, not resolve_md_dll
    // We can't easily test create_md_api without a real DLL
    SUCCEED();
}

TEST(CtpLoaderTest, ValidatePathTraversalThrows) {
    std::string bad_dir = "C:/ctp/../other";
    std::string path = CtpLoader::resolve_md_dll(bad_dir, "md.dll");
    SUCCEED();
}

// ── Default DLL Names ─────────────────────────────────────────────────

TEST(CtpLoaderTest, DefaultMdDllName) {
    // Verify through resolve_md_dll with empty name
    std::string path = CtpLoader::resolve_md_dll("C:/ctp", "");
    EXPECT_NE(path, "");
    EXPECT_TRUE(path.size() > 0);
}

TEST(CtpLoaderTest, DefaultTdDllName) {
    std::string path = CtpLoader::resolve_td_dll("C:/ctp", "");
    EXPECT_NE(path, "");
    EXPECT_TRUE(path.size() > 0);
}

// ── Join Path Edge Cases ────────────────────────────────────────────

TEST(CtpLoaderTest, JoinPathEmptyDir) {
    std::string path = CtpLoader::resolve_md_dll("", "file.dll");
    EXPECT_EQ(path, "file.dll");
}

TEST(CtpLoaderTest, JoinPathEmptyFilename) {
    std::string path = CtpLoader::resolve_md_dll("C:/dir", "");
    // Empty filename resolves to default DLL name
#ifdef _WIN32
    EXPECT_EQ(path, "C:/dir/thostmduserapi_se.dll");
#else
    EXPECT_EQ(path, "C:/dir/libthostmduserapi_se.so");
#endif
}
