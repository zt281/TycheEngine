// Unit tests for TdSpiImpl - tests methods that don't require td_api_ calls.

#include <gtest/gtest.h>

#include "modules/ctp_gateway_cpp/src/td_spi.h"
#include "modules/ctp_gateway_cpp/src/config.h"

#include <cstring>
#include <thread>
#include <chrono>

// ── Construction ──────────────────────────────────────────────────────

TEST(TdSpiTest, Construction) {
    GatewayConfig cfg;
    cfg.broker_id = "9999";
    cfg.user_id = "testuser";
    cfg.password = "testpass";

    TdSpiImpl spi(cfg, nullptr);
    EXPECT_FALSE(spi.is_logged_in());
}

// ── Authentication Response ───────────────────────────────────────────

TEST(TdSpiTest, OnRspAuthenticateSuccess) {
    GatewayConfig cfg;
    cfg.appid = "test_app";

    TdSpiImpl spi(cfg, nullptr);

    CThostFtdcRspAuthenticateField auth{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspAuthenticate(&auth, &info, 1, true);
    SUCCEED();
}

TEST(TdSpiTest, OnRspAuthenticateFailure) {
    GatewayConfig cfg;
    cfg.appid = "test_app";

    TdSpiImpl spi(cfg, nullptr);

    CThostFtdcRspAuthenticateField auth{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 1;
    std::strncpy(info.ErrorMsg, "Auth failed", sizeof(info.ErrorMsg) - 1);

    spi.OnRspAuthenticate(&auth, &info, 1, true);
    EXPECT_FALSE(spi.is_logged_in());
}

// ── Login Response ────────────────────────────────────────────────────

TEST(TdSpiTest, OnRspUserLoginSuccess) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    CThostFtdcRspUserLoginField login{};
    std::strncpy(login.TradingDay, "20250115", sizeof(login.TradingDay) - 1);
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspUserLogin(&login, &info, 1, true);
    EXPECT_TRUE(spi.is_logged_in());
}

TEST(TdSpiTest, OnRspUserLoginFailure) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    CThostFtdcRspUserLoginField login{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 1;
    std::strncpy(info.ErrorMsg, "Login failed", sizeof(info.ErrorMsg) - 1);

    spi.OnRspUserLogin(&login, &info, 1, true);
    EXPECT_FALSE(spi.is_logged_in());
}

TEST(TdSpiTest, OnRspUserLogout) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    CThostFtdcUserLogoutField logout{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;

    spi.OnRspUserLogout(&logout, &info, 1, true);
    SUCCEED();
}

// ── Front Disconnected ────────────────────────────────────────────────

TEST(TdSpiTest, OnFrontDisconnectedResetsLogin) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    // Simulate login success first
    CThostFtdcRspUserLoginField login{};
    CThostFtdcRspInfoField info{};
    info.ErrorID = 0;
    spi.OnRspUserLogin(&login, &info, 1, true);
    EXPECT_TRUE(spi.is_logged_in());

    spi.OnFrontDisconnected(0);
    EXPECT_FALSE(spi.is_logged_in());
}

// ── Wait for Login ────────────────────────────────────────────────────

TEST(TdSpiTest, WaitForLoginTimeout) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    // Not logged in, should timeout
    EXPECT_FALSE(spi.wait_for_login(0));
}

TEST(TdSpiTest, WaitForLoginSuccess) {
    GatewayConfig cfg;
    TdSpiImpl spi(cfg, nullptr);

    // Simulate login in a separate thread
    std::thread login_thread([&spi] {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        CThostFtdcRspUserLoginField login{};
        CThostFtdcRspInfoField info{};
        info.ErrorID = 0;
        spi.OnRspUserLogin(&login, &info, 1, true);
    });

    EXPECT_TRUE(spi.wait_for_login(5));
    EXPECT_TRUE(spi.is_logged_in());
    login_thread.join();
}
