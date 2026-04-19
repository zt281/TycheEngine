"""OpenCTP simulated trading gateway (模拟盘).

Connects to OpenCTP's free simulation servers which provide a CTP-compatible
interface with 7x24 or regular-hours environments.
"""

from typing import Any, Optional

from modules.trading.gateway.ctp.gateway import CtpGateway
from tyche.types import Endpoint


class CtpSimGateway(CtpGateway):
    """OpenCTP simulated trading gateway.

    Pre-configured with OpenCTP public server addresses.  No authentication
    code is required — only ``user_id`` and ``password`` (register at
    https://openctp.cn).

    Args:
        engine_endpoint: ZMQ endpoint of the TycheEngine broker.
        user_id: OpenCTP account user ID.
        password: OpenCTP account password.
        env: Server environment — ``"7x24"`` (round-the-clock) or ``"sim"``
            (regular trading hours).
        broker_id: CTP broker ID (default ``"9999"``).
        venue_name: Venue identifier used in instrument IDs (default ``"openctp"``).
        module_id: Optional TycheModule ID override.
    """

    ENVS = {
        "7x24": {
            "td_front": "tcp://trading.openctp.cn:30001",
            "md_front": "tcp://trading.openctp.cn:30011",
        },
        "sim": {
            "td_front": "tcp://trading.openctp.cn:30002",
            "md_front": "tcp://trading.openctp.cn:30012",
        },
    }

    def __init__(
        self,
        engine_endpoint: Endpoint,
        user_id: str,
        password: str,
        env: str = "7x24",
        broker_id: str = "9999",
        venue_name: str = "openctp",
        module_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        if env not in self.ENVS:
            raise ValueError(f"Unknown env {env!r}, choose from {list(self.ENVS)}")
        env_config = self.ENVS[env]
        super().__init__(
            engine_endpoint=engine_endpoint,
            venue_name=venue_name,
            broker_id=broker_id,
            user_id=user_id,
            password=password,
            td_front=env_config["td_front"],
            md_front=env_config["md_front"],
            require_auth=False,  # OpenCTP doesn't require auth
            module_id=module_id,
            **kwargs,
        )
