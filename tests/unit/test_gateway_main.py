"""Unit tests for CTP gateway runner entry point."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from modules.trading.gateway.ctp.gateway_main import build_gateway, main, parse_args


def _make_mock_module(cls_name: str):
    mod = MagicMock()
    setattr(mod, cls_name, MagicMock())
    return mod


class TestParseArgs:
    def test_config_arg(self):
        args = parse_args(["--config", "/path/to/config.json"])
        assert args.config == "/path/to/config.json"

    def test_default_no_config(self):
        args = parse_args([])
        assert args.config is None

    def test_sim_shortcut_args(self):
        args = parse_args([
            "--sim", "--user-id", "u", "--password", "p",
            "--instruments", "rb2410", "cu2410",
        ])
        assert args.sim is True
        assert args.user_id == "u"
        assert args.password == "p"
        assert args.instruments == ["rb2410", "cu2410"]

    def test_live_shortcut_args(self):
        args = parse_args([
            "--live",
            "--user-id", "u", "--password", "p",
            "--td-front", "tcp://1.2.3.4:1",
            "--md-front", "tcp://1.2.3.4:2",
        ])
        assert args.live is True
        assert args.td_front == "tcp://1.2.3.4:1"
        assert args.md_front == "tcp://1.2.3.4:2"


class TestBuildGateway:
    def test_build_sim_gateway(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "u", "password": "p", "env": "7x24"},
        }))
        mock_mod = _make_mock_module("CtpSimGateway")
        with patch.dict(sys.modules, {"modules.trading.gateway.ctp.sim": mock_mod}):
            gw = build_gateway(str(config_path), {})
            mock_mod.CtpSimGateway.assert_called_once()
            assert gw == mock_mod.CtpSimGateway.return_value

    def test_build_live_gateway(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "live",
            "live": {
                "user_id": "u", "password": "p",
                "td_front": "tcp://1.2.3.4:1",
                "md_front": "tcp://1.2.3.4:2",
            },
        }))
        mock_mod = _make_mock_module("CtpLiveGateway")
        with patch.dict(sys.modules, {"modules.trading.gateway.ctp.live": mock_mod}):
            gw = build_gateway(str(config_path), {})
            mock_mod.CtpLiveGateway.assert_called_once()
            assert gw == mock_mod.CtpLiveGateway.return_value

    def test_cli_overrides_applied(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "gateway_type": "sim",
            "sim": {"user_id": "file_u", "password": "p"},
        }))
        mock_mod = _make_mock_module("CtpSimGateway")
        with patch.dict(sys.modules, {"modules.trading.gateway.ctp.sim": mock_mod}):
            build_gateway(str(config_path), {"user_id": "cli_u"})
            call_kwargs = mock_mod.CtpSimGateway.call_args.kwargs
            assert call_kwargs["user_id"] == "cli_u"
