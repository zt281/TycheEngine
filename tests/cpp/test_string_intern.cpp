// Unit tests for tyche::StringIntern - fast string interning.

#include <gtest/gtest.h>

#include <string>
#include <thread>
#include <vector>

#include "tyche/cpp/string_intern.h"

namespace tyche {
namespace {

// ── Basic intern / lookup / resolve ───────────────────────────────────

TEST(StringInternTest, InternReturnsId) {
    StringIntern intern;
    InternId id = intern.intern("hello");
    EXPECT_NE(id, INVALID_INTERN_ID);
}

TEST(StringInternTest, InternSameStringReturnsSameId) {
    StringIntern intern;
    InternId id1 = intern.intern("test");
    InternId id2 = intern.intern("test");
    EXPECT_EQ(id1, id2);
}

TEST(StringInternTest, InternDifferentStringsReturnsDifferentIds) {
    StringIntern intern;
    InternId id1 = intern.intern("alpha");
    InternId id2 = intern.intern("beta");
    EXPECT_NE(id1, id2);
}

TEST(StringInternTest, LookupExistingReturnsId) {
    StringIntern intern;
    InternId id = intern.intern("find_me");
    EXPECT_EQ(intern.lookup("find_me"), id);
}

TEST(StringInternTest, LookupNonexistentReturnsInvalid) {
    StringIntern intern;
    EXPECT_EQ(intern.lookup("missing"), INVALID_INTERN_ID);
}

TEST(StringInternTest, ResolveExistingReturnsString) {
    StringIntern intern;
    InternId id = intern.intern("resolve_me");
    EXPECT_EQ(intern.resolve(id), "resolve_me");
}

TEST(StringInternTest, ResolveInvalidReturnsEmpty) {
    StringIntern intern;
    EXPECT_EQ(intern.resolve(INVALID_INTERN_ID), "");
    EXPECT_EQ(intern.resolve(99999), "");
}

TEST(StringInternTest, ResolveUnassignedIdReturnsEmpty) {
    StringIntern intern;
    // ID 1 is reserved but never assigned since we intern nothing
    EXPECT_EQ(intern.resolve(1), "");
}

// ── Size tracking ─────────────────────────────────────────────────────

TEST(StringInternTest, SizeTracksInternedCount) {
    StringIntern intern;
    EXPECT_EQ(intern.size(), 0u);
    intern.intern("a");
    EXPECT_EQ(intern.size(), 1u);
    intern.intern("b");
    EXPECT_EQ(intern.size(), 2u);
    intern.intern("a");  // duplicate
    EXPECT_EQ(intern.size(), 2u);
}

// ── String view support ───────────────────────────────────────────────

TEST(StringInternTest, InternStringView) {
    StringIntern intern;
    std::string s = "string_view_test";
    InternId id1 = intern.intern(s);
    InternId id2 = intern.intern(std::string_view(s));
    EXPECT_EQ(id1, id2);
}

// ── Large scale interning ─────────────────────────────────────────────

TEST(StringInternTest, InternManyStrings) {
    StringIntern intern;
    constexpr int N = 10000;

    for (int i = 0; i < N; ++i) {
        intern.intern("str_" + std::to_string(i));
    }

    EXPECT_EQ(intern.size(), static_cast<size_t>(N));

    // All should be resolvable
    for (int i = 0; i < N; ++i) {
        InternId id = intern.lookup("str_" + std::to_string(i));
        EXPECT_NE(id, INVALID_INTERN_ID);
        EXPECT_EQ(intern.resolve(id), "str_" + std::to_string(i));
    }
}

TEST(StringInternTest, InternManyThreads) {
    StringIntern intern;
    constexpr int NUM_THREADS = 100;
    constexpr int STRINGS_PER_THREAD = 100;

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&intern, t, STRINGS_PER_THREAD] {
            for (int i = 0; i < STRINGS_PER_THREAD; ++i) {
                intern.intern("thread_" + std::to_string(t) + "_" + std::to_string(i));
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(intern.size(), static_cast<size_t>(NUM_THREADS * STRINGS_PER_THREAD));
}

TEST(StringInternTest, ConcurrentInternSameString) {
    StringIntern intern;
    constexpr int NUM_THREADS = 50;

    std::vector<std::thread> threads;
    for (int t = 0; t < NUM_THREADS; ++t) {
        threads.emplace_back([&intern] {
            intern.intern("shared_key");
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(intern.size(), 1u);
    EXPECT_EQ(intern.lookup("shared_key"), intern.intern("shared_key"));
}

TEST(StringInternTest, ConcurrentReadWrite) {
    StringIntern intern;
    constexpr int NUM_THREADS = 20;

    // Pre-intern some strings
    for (int i = 0; i < 50; ++i) {
        intern.intern("pre_" + std::to_string(i));
    }

    std::vector<std::thread> threads;

    // Writers
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&intern, t] {
            for (int i = 0; i < 100; ++i) {
                intern.intern("writer_" + std::to_string(t) + "_" + std::to_string(i));
            }
        });
    }

    // Readers
    for (int t = 0; t < NUM_THREADS / 2; ++t) {
        threads.emplace_back([&intern, t] {
            for (int i = 0; i < 100; ++i) {
                intern.lookup("pre_" + std::to_string(i % 50));
                intern.resolve(static_cast<InternId>((i % 50) + 1));
                intern.size();
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    // Should not crash; size should be consistent
    EXPECT_GE(intern.size(), 50u);
}

// ── Empty string ──────────────────────────────────────────────────────

TEST(StringInternTest, EmptyString) {
    StringIntern intern;
    InternId id = intern.intern("");
    EXPECT_NE(id, INVALID_INTERN_ID);
    EXPECT_EQ(intern.lookup(""), id);
    EXPECT_EQ(intern.resolve(id), "");
}

// ── Id monotonicity ────────────────────────────────────────────────────

TEST(StringInternTest, IdsAreMonotonicallyIncreasing) {
    StringIntern intern;
    InternId prev = INVALID_INTERN_ID;
    for (int i = 0; i < 100; ++i) {
        InternId id = intern.intern("mono_" + std::to_string(i));
        EXPECT_GT(id, prev);
        prev = id;
    }
}

}  // namespace
}  // namespace tyche
