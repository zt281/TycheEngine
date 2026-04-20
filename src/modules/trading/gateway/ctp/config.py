"""CTP gateway configuration loader.

Loads config from JSON file, with overrides from environment variables
and CLI arguments. Priority: CLI > env > JSON > defaults.
"""
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GatewayType(Enum):
    """Gateway mode."""
    SIM = "sim"
    LIVE = "live"


@dataclass
class GatewayConfig:
    """Resolved gateway configuration."""
    gateway_type: GatewayType
    engine_host: str = "127.0.0.1"
    engine_registration_port: int = 5555
    engine_heartbeat_port: int = 5559
    sim_user_id: str = ""
    sim_password: str = ""
    sim_env: str = "7x24"
    sim_broker_id: str = "9999"
    live_user_id: str = ""
    live_password: str = ""
    live_broker_id: str = ""
    live_td_front: str = ""
    live_md_front: str = ""
    live_auth_code: Optional[str] = None
    live_app_id: Optional[str] = None
    instruments: List[str] = field(default_factory=list)
    reconnect_enabled: bool = True
    reconnect_max_retries: int = 10
    reconnect_base_delay_ms: int = 1000
    reconnect_max_delay_ms: int = 30000

    def __post_init__(self):
        if self.gateway_type == GatewayType.LIVE:
            if not self.live_td_front or not self.live_md_front:
                raise ValueError("live gateway requires 'live_td_front' and 'live_md_front'")


def load_config(
    config_path: Optional[str] = None,
    cli_args: Optional[Dict[str, Any]] = None,
) -> GatewayConfig:
    """Load gateway configuration with override priority: CLI > env > JSON > defaults."""
    raw: Dict[str, Any] = {}

    if config_path:
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    env_prefix = "TYCHE_GATEWAY_"
    env_map = {
        "USER_ID": ["sim", "user_id"],
        "PASSWORD": ["sim", "password"],
        "BROKER_ID": ["sim", "broker_id"],
    }
    for env_key, json_path in env_map.items():
        val = os.environ.get(f"{env_prefix}{env_key}")
        if val is not None:
            _set_nested(raw, json_path, val)

    live_env_map = {
        "LIVE_USER_ID": ["live", "user_id"],
        "LIVE_PASSWORD": ["live", "password"],
        "LIVE_BROKER_ID": ["live", "broker_id"],
        "LIVE_TD_FRONT": ["live", "td_front"],
        "LIVE_MD_FRONT": ["live", "md_front"],
        "LIVE_AUTH_CODE": ["live", "auth_code"],
        "LIVE_APP_ID": ["live", "app_id"],
    }
    for env_key, json_path in live_env_map.items():
        val = os.environ.get(f"{env_prefix}{env_key}")
        if val is not None:
            _set_nested(raw, json_path, val)

    cli_map = {
        "user_id": ["sim", "user_id"],
        "password": ["sim", "password"],
        "broker_id": ["sim", "broker_id"],
        "instruments": ["instruments"],
    }
    if cli_args:
        for key, val in cli_args.items():
            if val is not None:
                path = cli_map.get(key, [key])
                _set_nested(raw, path, val)

    return _build_config(raw)


def _set_nested(d: Dict[str, Any], path: List[str], value: Any) -> None:
    for key in path[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[path[-1]] = value


def _build_config(raw: Dict[str, Any]) -> GatewayConfig:
    gateway_type = GatewayType(raw.get("gateway_type", "sim"))
    engine = raw.get("engine", {})
    sim = raw.get("sim", {})
    live = raw.get("live", {})
    reconnect = raw.get("reconnect", {})
    instruments = raw.get("instruments", [])

    return GatewayConfig(
        gateway_type=gateway_type,
        engine_host=engine.get("host", "127.0.0.1"),
        engine_registration_port=engine.get("registration_port", 5555),
        engine_heartbeat_port=engine.get("heartbeat_port", 5559),
        sim_user_id=sim.get("user_id", ""),
        sim_password=sim.get("password", ""),
        sim_env=sim.get("env", "7x24"),
        sim_broker_id=sim.get("broker_id", "9999"),
        live_user_id=live.get("user_id", ""),
        live_password=live.get("password", ""),
        live_broker_id=live.get("broker_id", ""),
        live_td_front=live.get("td_front", ""),
        live_md_front=live.get("md_front", ""),
        live_auth_code=live.get("auth_code"),
        live_app_id=live.get("app_id"),
        instruments=instruments,
        reconnect_enabled=reconnect.get("enabled", True),
        reconnect_max_retries=reconnect.get("max_retries", 10),
        reconnect_base_delay_ms=reconnect.get("base_delay_ms", 1000),
        reconnect_max_delay_ms=reconnect.get("max_delay_ms", 30000),
    )
