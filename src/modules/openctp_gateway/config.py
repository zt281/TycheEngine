"""OpenCTP Gateway configuration."""

import json
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class GatewayConfig:
    """Configuration for OpenCTP Gateway module.

    Supports both futures (tts-future) and stocks (tts-stock) gateway types.
    """

    # Engine connection
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555

    # Gateway type: "futures" or "stocks"
    gateway_type: str = "futures"

    # CTP front addresses
    md_front: str = ""
    td_front: str = ""

    # Authentication
    broker_id: str = ""
    user_id: str = ""
    password: str = ""

    # Underlying products to subscribe: {exchange: [product_id, ...]}
    underlyings: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> "GatewayConfig":
        """Load configuration from a JSON file.

        Expected format:
            {
                "engine": {"host": "127.0.0.1", "port": 5555},
                "gateway": {
                    "gateway_type": "futures",
                    "md_front": "tcp://...",
                    "td_front": "tcp://...",
                    "broker_id": "",
                    "user_id": "",
                    "password": "",
                    "underlyings": {"SHFE": ["ag", "au"]}
                }
            }
        """
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        engine_cfg = raw.get("engine", {})
        gw_cfg = raw.get("gateway", {})

        defaults = cls()
        return cls(
            engine_host=engine_cfg.get("host", defaults.engine_host),
            engine_port=engine_cfg.get("port", defaults.engine_port),
            gateway_type=gw_cfg.get("gateway_type", defaults.gateway_type),
            md_front=gw_cfg.get("md_front", defaults.md_front),
            td_front=gw_cfg.get("td_front", defaults.td_front),
            broker_id=gw_cfg.get("broker_id", defaults.broker_id),
            user_id=gw_cfg.get("user_id", defaults.user_id),
            password=gw_cfg.get("password", defaults.password),
            underlyings=gw_cfg.get("underlyings", defaults.underlyings),
        )
