"""OpenCTP Gateway configuration."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class GatewayConfig:
    """Configuration for OpenCTP Gateway module.

    Defaults point to the OpenCTP 24h simulation environment.

    Instead of listing specific instrument IDs, configure underlyings
    as a mapping of exchange_id -> list of product_ids. The gateway
    queries the static_data module at startup to resolve all instrument
    IDs, then subscribes via CTP.

    Options subscription:
        By default only futures (ProductClass=1) are subscribed.
        Set ``subscribe_options`` to True to also subscribe options
        (ProductClass=2) for the configured underlyings.
    """

    md_front: str = "tcp://122.51.136.165:20004"  # 24h 行情前置
    td_front: str = "tcp://122.51.136.165:20002"  # 24h 交易前置
    broker_id: str = ""
    user_id: str = "test"
    password: str = "test"
    underlyings: Dict[str, List[str]] = field(default_factory=dict)
    # Subscribe to options (ProductClass=2) in addition to futures (ProductClass=1)
    subscribe_options: bool = False
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555
    # Timeout for querying static_data module (seconds)
    resolve_timeout: float = 10.0
