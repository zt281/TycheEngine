// Unit tests for MdSpiImpl - tests methods that don't require md_api_ calls.

#include <gtest/gtest.h>

#include "modules/ctp_gateway_cpp/src/md_spi.h"
#include "modules/ctp_gateway_cpp/src/config.h"

#include <cstring>

// ── Construction ──────────────────────────────────────────────────────

TEST(MdSpiTest, Construction) {
    GatewayConfig cfg;
    cfg.broker_id = "9999";
    cfg.user_id = "testuser";
    cfg.password = "testpass";

    bool quote_received = false;
    MdSpiImpl spi(cfg, nullptr, [&quote_received](const tyche::Payload&) {
        quote_received = true;
    });

    // MdSpiImpl does not have is_logged_in() public method
    SUCCEED();
}

// ── Connection / Disconnection ────────────────────────────────────────

TEST(MdSpiTest, OnFrontDisconnected) {
    GatewayConfig cfg;
    cfg.broker_id = "9999";
    cfg.user_id = "testuser";
    cfg.password = "testpass";

    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    // Should not crash
    spi.OnFrontDisconnected(0);
    SUCCEED();
}

TEST(MdSpiTest, OnHeartBeatWarning) {
    GatewayConfig cfg;
    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    // Should not crash
    spi.OnHeartBeatWarning(30);
    SUCCEED();
}

// ── Login Response ──────────────────────────────────────────────────────

TEST(MdSpiTest, OnRspUserLoginSuccess) {
    GatewayConfig cfg;
    cfg.broker_id = "9999";
    cfg.user_id = "testuser";
    cfg.password = "testpass";

    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    CThostFtdcRspUserLoginField login{};
    std::strncpy(login.TradingDay, "20250115", sizeof(login.TradingDay) - 1);
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspUserLogin(&login, &info, 1, true);
    SUCCEED();
}

TEST(MdSpiTest, OnRspUserLoginFailure) {
    GatewayConfig cfg;
    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    CThostFtdcRspUserLoginField login{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 1;
    std::strncpy(info.ErrorMsg, "Login failed", sizeof(info.ErrorMsg) - 1);

    spi.OnRspUserLogin(&login, &info, 1, true);
    SUCCEED();
}

TEST(MdSpiTest, OnRspUserLogout) {
    GatewayConfig cfg;
    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    CThostFtdcUserLogoutField logout{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspUserLogout(&logout, &info, 1, true);
    SUCCEED();
}

// ── Subscription Response ─────────────────────────────────────────────

TEST(MdSpiTest, OnRspSubMarketData) {
    GatewayConfig cfg;
    MdSpiImpl spi(cfg, nullptr, [](const tyche::Payload&) {});

    CThostFtdcSpecificInstrumentField inst{};
    std::strncpy(inst.InstrumentID, "ag2506", sizeof(inst.InstrumentID) - 1);
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspSubMarketData(&inst, &info, 1, true);
    SUCCEED();
}

// ── Depth Market Data ─────────────────────────────────────────────────

TEST(MdSpiTest, OnRtnDepthMarketData) {
    GatewayConfig cfg;

    bool quote_received = false;
    MdSpiImpl spi(cfg, nullptr, [&quote_received](const tyche::Payload&) {
        quote_received = true;
    });

    CThostFtdcDepthMarketDataField data{};
    std::strncpy(data.InstrumentID, "ag2506", sizeof(data.InstrumentID) - 1);
    data.LastPrice = 5000.0;
    data.BidPrice1 = 4999.0;
    data.AskPrice1 = 5001.0;
    data.BidVolume1 = 10;
    data.AskVolume1 = 5;
    data.Volume = 100;
    std::strncpy(data.UpdateTime, "09:00:01", sizeof(data.UpdateTime) - 1);
    data.UpdateMillisec = 500;

    spi.OnRtnDepthMarketData(&data);
    EXPECT_TRUE(quote_received);
}

TEST(MdSpiTest, OnRtnDepthMarketDataPayloadContent) {
    GatewayConfig cfg;

    tyche::Payload received_payload;
    MdSpiImpl spi(cfg, nullptr, [&received_payload](const tyche::Payload& p) {
        received_payload = p;
    });

    CThostFtdcDepthMarketDataField data{};
    std::strncpy(data.InstrumentID, "ag2506", sizeof(data.InstrumentID) - 1);
    data.LastPrice = 5000.0;
    data.BidPrice1 = 4999.0;
    data.AskPrice1 = 5001.0;
    data.BidVolume1 = 10;
    data.AskVolume1 = 5;
    data.Volume = 100;
    std::strncpy(data.UpdateTime, "09:00:01", sizeof(data.UpdateTime) - 1);
    data.UpdateMillisec = 500;
    data.OpenInterest = 50000.0;
    data.Turnover = 1000000.0;
    data.UpperLimitPrice = 5500.0;
    data.LowerLimitPrice = 4500.0;
    std::strncpy(data.TradingDay, "20250115", sizeof(data.TradingDay) - 1);
    std::strncpy(data.ExchangeID, "SHFE", sizeof(data.ExchangeID) - 1);

    spi.OnRtnDepthMarketData(&data);

    EXPECT_FALSE(received_payload.empty());
    EXPECT_NE(received_payload.find("instrument_id"), received_payload.end());
    EXPECT_NE(received_payload.find("last_price"), received_payload.end());
    EXPECT_NE(received_payload.find("bid_price1"), received_payload.end());
    EXPECT_NE(received_payload.find("ask_price1"), received_payload.end());
}
