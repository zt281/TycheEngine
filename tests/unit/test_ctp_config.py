"""Unit tests for CTP gateway config loader."""
import json
import os
from pathlib import Path
import pytest
from modules.trading.gateway.ctp.config import GatewayConfig, GatewayType, load_config


class TestGatewayType:
    def test_sim_value(self):
        assert GatewayType.SIM.value == "sim"

    def test_live_value(self):
        assert GatewayType.LIVE.value == "live"


class TestGatewayConfigDefaults:
    def test_sim_defaults(self):
        cfg = GatewayConfig(
            gateway_type=GatewayType.SIM,
            sim_user_id="u",
            sim_password="p",
        )
        assert cfg.sim_env == "7x24"
        assert cfg.sim_broker_id == "9999"
        assert cfg.engine_host == "127.0.0.1"
        assert cfg.engine_registration_port == 5555
        assert cfg.engine_heartbeat_port == 5559
        assert cfg.instruments == []
        assert cfg.reconnect_enabled is True
        assert cfg.reconnect_max_retries == 10

    def test_live_requires_fronts(self):
        with pytest.raises(ValueError, match="td_front"):
            GatewayConfig(
                gateway_type=GatewayType.LIVE,
                live_user_id="u",
                live_password="p",
            )

    def test_live_with_fronts(self):
        cfg = GatewayConfig(
            gateway_type=GatewayType.LIVE,
            live_user_id="u",
            live_password="p",
            live_td_front="tcp://1.2.3.4:10201",
            live_md_front="tcp://1.2.3.4:10211",
        )
        assert cfg.live_td_front == "tcp://1.2.3.4:10201"
        assert cfg.live_md_front == "tcp://1.2.3.4:10211"


class TestLoadConfigFromJson:
    def test_load_sim_config(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "engine": {
                "host": "127.0.0.1",
                "registration_port": 5555,
                "heartbeat_port": 5559,
            },
            "sim": {
                "user_id": "test_user",
                "password": "test_pass",
                "env": "7x24",
                "broker_id": "9999",
            },
            "instruments": ["rb2410", "cu2410"],
            "reconnect": {
                "enabled": True,
                "max_retries": 10,
                "base_delay_ms": 1000,
                "max_delay_ms": 30000,
            },
        }))
        cfg = load_config(str(config_path))
        assert cfg.gateway_type == GatewayType.SIM
        assert cfg.sim_user_id == "test_user"
        assert cfg.sim_password == "test_pass"
        assert cfg.instruments == ["rb2410", "cu2410"]
        assert cfg.reconnect_max_retries == 10

    def test_load_live_config(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "live",
            "live": {
                "user_id": "live_user",
                "password": "live_pass",
                "broker_id": "1234",
                "td_front": "tcp://180.168.146.187:10201",
                "md_front": "tcp://180.168.146.187:10211",
                "auth_code": "AUTH",
                "app_id": "APP",
            },
        }))
        cfg = load_config(str(config_path))
        assert cfg.gateway_type == GatewayType.LIVE
        assert cfg.live_td_front == "tcp://180.168.146.187:10201"
        assert cfg.live_auth_code == "AUTH"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.json")

    def test_invalid_json_raises(self, tmp_path: Path):
        config_path = tmp_path / "bad.json"
        config_path.write_text("not json")
        with pytest.raises(ValueError):
            load_config(str(config_path))


class TestEnvVarOverrides:
    def test_env_override_user_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TYCHE_GATEWAY_USER_ID", "env_user")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "file_user", "password": "pass"},
        }))
        cfg = load_config(str(config_path))
        assert cfg.sim_user_id == "env_user"

    def test_env_override_password(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TYCHE_GATEWAY_PASSWORD", "env_pass")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "u", "password": "file_pass"},
        }))
        cfg = load_config(str(config_path))
        assert cfg.sim_password == "env_pass"

    def test_env_override_broker_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TYCHE_GATEWAY_BROKER_ID", "8888")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "u", "password": "p", "broker_id": "9999"},
        }))
        cfg = load_config(str(config_path))
        assert cfg.sim_broker_id == "8888"


class TestCliOverrides:
    def test_cli_override_user_id(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "file_user", "password": "pass"},
        }))
        cfg = load_config(str(config_path), cli_args={"user_id": "cli_user"})
        assert cfg.sim_user_id == "cli_user"

    def test_cli_override_instruments(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "u", "password": "p"},
            "instruments": ["rb2410"],
        }))
        cfg = load_config(str(config_path), cli_args={"instruments": ["cu2410", "au2412"]})
        assert cfg.instruments == ["cu2410", "au2412"]

    def test_override_priority_cli_beats_env(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TYCHE_GATEWAY_USER_ID", "env_user")
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "file_user", "password": "pass"},
        }))
        cfg = load_config(str(config_path), cli_args={"user_id": "cli_user"})
        assert cfg.sim_user_id == "cli_user"
