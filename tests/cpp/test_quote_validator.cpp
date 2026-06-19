// Unit tests for QuoteValidator - data quality validation.

#include <gtest/gtest.h>

#include "modules/ctp_gateway_cpp/src/quote_validator.h"
#include "modules/ctp_gateway_cpp/src/quote_tick.h"

#include <cstring>

// Helper to create a QuoteTick with minimal initialization
QuoteTick make_tick(const char* instrument,
                    double last_price,
                    double upper_limit,
                    double lower_limit,
                    const char* update_time,
                    int update_ms,
                    int volume,
                    const char* trading_day) {
    QuoteTick tick{};
    std::strncpy(tick.instrument_id, instrument, sizeof(tick.instrument_id) - 1);
    tick.last_price = last_price;
    tick.upper_limit_price = upper_limit;
    tick.lower_limit_price = lower_limit;
    std::strncpy(tick.update_time, update_time, sizeof(tick.update_time) - 1);
    tick.update_millisec = update_ms;
    tick.volume = volume;
    std::strncpy(tick.trading_day, trading_day, sizeof(tick.trading_day) - 1);
    return tick;
}

// ── First tick (no predecessor) ───────────────────────────────────────

TEST(QuoteValidatorTest, FirstTickAlwaysValid) {
    auto tick = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 100, 100, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(tick, nullptr));
}

TEST(QuoteValidatorTest, PrevWithZeroPriceAlwaysValid) {
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 100, 100, "20250115");
    QuoteTick prev{};
    prev.last_price = 0.0;
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

// ── Cross-day detection ───────────────────────────────────────────────

TEST(QuoteValidatorTest, CrossDayVolumeDecreaseAllowed) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "15:00:00", 0, 1000, "20250114");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 500, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, SameDayVolumeDecreaseInvalid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 1000, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 500, "20250115");
    EXPECT_FALSE(QuoteValidator::validate(current, &prev));
}

// ── Price jump checks ─────────────────────────────────────────────────

TEST(QuoteValidatorTest, SmallPriceJumpValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5100.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    // 5100/5000 = 1.02 (2% jump) < 10%
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, LargePriceJumpInvalid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 6000.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    // 6000/5000 = 1.20 (20% jump) > 10% and outside limits
    EXPECT_FALSE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, LargePriceJumpWithinLimitsValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5400.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    // 5400/5000 = 1.08 (8% jump) < 10% but within limits
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, PriceJumpAtLimitValid) {
    auto prev = make_tick("ag2506", 5500.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    // prev was at upper limit
    auto current = make_tick("ag2506", 5500.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, NoLimitsDefinedValid) {
    auto prev = make_tick("ag2506", 5000.0, 0.0, 0.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 6000.0, 0.0, 0.0, "09:00:01", 0, 200, "20250115");
    // No limits defined, should pass
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

// ── Timestamp regression ──────────────────────────────────────────────

TEST(QuoteValidatorTest, TimestampRegressionInvalid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 500, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 200, "20250115");
    EXPECT_FALSE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, TimestampProgressionValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 500, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, SameTimestampValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, InvalidTimeFormatSkipsCheck) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "bad_time", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "also_bad", 0, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

// ── Volume increase ───────────────────────────────────────────────────

TEST(QuoteValidatorTest, VolumeIncreaseValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, SameVolumeValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:01", 0, 100, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

// ── Combined checks ───────────────────────────────────────────────────

TEST(QuoteValidatorTest, AllGoodValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 5050.0, 5500.0, 4500.0, "09:00:01", 500, 200, "20250115");
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, NegativePriceJumpValid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 4800.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    // 4800/5000 = 0.96 (4% drop) < 10%
    EXPECT_TRUE(QuoteValidator::validate(current, &prev));
}

TEST(QuoteValidatorTest, LargeNegativePriceJumpInvalid) {
    auto prev = make_tick("ag2506", 5000.0, 5500.0, 4500.0, "09:00:00", 0, 100, "20250115");
    auto current = make_tick("ag2506", 3900.0, 5500.0, 4500.0, "09:00:01", 0, 200, "20250115");
    // 3900/5000 = 0.78 (22% drop) > 10% and outside limits
    EXPECT_FALSE(QuoteValidator::validate(current, &prev));
}
