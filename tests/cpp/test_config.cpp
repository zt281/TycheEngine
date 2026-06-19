// Unit tests for GatewayConfig::from_file - configuration parsing.

#include <gtest/gtest.h>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

#include "modules/ctp_gateway_cpp/src/config.h"

namespace fs = std::filesystem;

class ConfigTest : public ::testing::Test {
protected:
    std::string temp_dir;

    void SetUp() override {
        temp_dir = (fs::temp_directory_path() / "tyche_test_config").string();
        fs::create_directories(temp_dir);
    }

    void TearDown() override {
        fs::remove_all(temp_dir);
    }

    std::string make_file(const std::string& name, const std::string& content) {
        std::string path = temp_dir + "/" + name;
        std::ofstream f(path);
        f << content;
        return path;
    }
};

// ── Valid Config ──────────────────────────────────────────────────────

TEST_F(ConfigTest, ValidConfig) {
    std::string json = R"({
        "engine": {"host": "127.0.0.1", "port": 5555},
        "gateway": {
            "family_name": "ctp_test",
            "md_front": "tcp://192.168.1.1:10001",
            "td_front": "tcp://192.168.1.1:10002",
            "broker_id": "9999",
            "user_id": "testuser",
            "password": "testpass",
            "appid": "test_app",
            "authcode": "test_auth",
            "dll_dir": "C:/ctp_dll",
            "md_dll": "md.dll",
            "td_dll": "td.dll",
            "reconnect_interval_secs": 10,
            "static_data_timeout_secs": 30,
            "underlyings": {"SHFE": ["ag", "au"]}
        }
    })";

    auto cfg = GatewayConfig::from_file(make_file("valid.json", json));
    EXPECT_EQ(cfg.engine_host, "127.0.0.1");
    EXPECT_EQ(cfg.engine_port, 5555);
    EXPECT_EQ(cfg.family_name, "ctp_test");
    EXPECT_EQ(cfg.md_front, "tcp://192.168.1.1:10001");
    EXPECT_EQ(cfg.td_front, "tcp://192.168.1.1:10002");
    EXPECT_EQ(cfg.broker_id, "9999");
    EXPECT_EQ(cfg.user_id, "testuser");
    EXPECT_TRUE(std::string(cfg.password.c_str()) == "testpass");
    EXPECT_EQ(cfg.appid, "test_app");
    EXPECT_EQ(cfg.authcode, "test_auth");
    EXPECT_EQ(cfg.dll_dir, "C:/ctp_dll");
    EXPECT_EQ(cfg.md_dll, "md.dll");
    EXPECT_EQ(cfg.td_dll, "td.dll");
    EXPECT_EQ(cfg.reconnect_interval_secs, 10);
    EXPECT_EQ(cfg.static_data_timeout_secs, 30);
    EXPECT_EQ(cfg.underlyings.size(), 1u);
    EXPECT_EQ(cfg.underlyings.at("SHFE").size(), 2u);
}

TEST_F(ConfigTest, MinimalValidConfig) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1",
            "broker_id": "b",
            "user_id": "u",
            "password": "p",
            "dll_dir": "C:/dll",
            "underlyings": {"DCE": ["i"]}
        }
    })";

    auto cfg = GatewayConfig::from_file(make_file("minimal.json", json));
    EXPECT_EQ(cfg.engine_host, "127.0.0.1");  // default
    EXPECT_EQ(cfg.engine_port, 5555);          // default
    EXPECT_EQ(cfg.family_name, "ctp_gateway"); // default
    EXPECT_EQ(cfg.reconnect_interval_secs, 5);  // default
    EXPECT_EQ(cfg.static_data_timeout_secs, 15); // default
}

// ── Invalid JSON ──────────────────────────────────────────────────────

TEST_F(ConfigTest, InvalidJsonThrows) {
    std::string json = "{ not valid json }";
    EXPECT_THROW(GatewayConfig::from_file(make_file("bad.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingFileThrows) {
    EXPECT_THROW(GatewayConfig::from_file("/nonexistent/path/config.json"), std::runtime_error);
}

// ── Missing Required Fields ───────────────────────────────────────────

TEST_F(ConfigTest, MissingGatewaySectionThrows) {
    std::string json = R"({"engine": {"host": "127.0.0.1"}})";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_gateway.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingMdFrontThrows) {
    std::string json = R"({
        "gateway": {
            "broker_id": "b", "user_id": "u", "password": "p",
            "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_md_front.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingBrokerIdThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "user_id": "u", "password": "p",
            "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_broker.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingUserIdThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "password": "p",
            "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_user.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingPasswordThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_pass.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingDllDirThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_dll.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, MissingUnderlyingsThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "dll_dir": "C:/dll"
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("no_underlyings.json", json)), std::runtime_error);
}

// ── Invalid Values ────────────────────────────────────────────────────

TEST_F(ConfigTest, InvalidEnginePortThrows) {
    std::string json = R"({
        "engine": {"port": 99999},
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("bad_port.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, ZeroEnginePortThrows) {
    std::string json = R"({
        "engine": {"port": 0},
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "dll_dir": "C:/dll", "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("zero_port.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, NegativeReconnectIntervalThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "dll_dir": "C:/dll",
            "reconnect_interval_secs": -1,
            "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("neg_reconnect.json", json)), std::runtime_error);
}

TEST_F(ConfigTest, ZeroStaticDataTimeoutThrows) {
    std::string json = R"({
        "gateway": {
            "md_front": "tcp://1.1.1.1:1", "broker_id": "b", "user_id": "u",
            "password": "p", "dll_dir": "C:/dll",
            "static_data_timeout_secs": 0,
            "underlyings": {"DCE": ["i"]}
        }
    })";
    EXPECT_THROW(GatewayConfig::from_file(make_file("zero_timeout.json", json)), std::runtime_error);
}

// ── secure_string ─────────────────────────────────────────────────────

TEST_F(ConfigTest, SecureStringClear) {
    secure_string s("secret");
    EXPECT_EQ(std::string(s.c_str()), "secret");
    s.clear();
    EXPECT_TRUE(s.empty());
}

TEST_F(ConfigTest, SecureStringAssignment) {
    secure_string s;
    s = "password123";
    EXPECT_EQ(std::string(s.c_str()), "password123");

    s = std::string("another");
    EXPECT_EQ(std::string(s.c_str()), "another");
}

TEST_F(ConfigTest, SecureStringMove) {
    secure_string s1("move_me");
    secure_string s2(std::move(s1));
    EXPECT_EQ(std::string(s2.c_str()), "move_me");
}
