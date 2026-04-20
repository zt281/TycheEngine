"""CTP gateway package — OpenCTP sim and live CTP broker gateways."""

from typing import List

__all__: List[str] = []

try:
    from modules.trading.gateway.ctp.config import GatewayConfig, GatewayType  # noqa: F401
    from modules.trading.gateway.ctp.gateway import CtpGateway  # noqa: F401
    from modules.trading.gateway.ctp.live import CtpLiveGateway  # noqa: F401
    from modules.trading.gateway.ctp.sim import CtpSimGateway  # noqa: F401
    from modules.trading.gateway.ctp.state_machine import (  # noqa: F401
        ConnectionState,
        ConnectionStateMachine,
        ReconnectConfig,
    )

    __all__ += [
        "CtpGateway",
        "CtpLiveGateway",
        "CtpSimGateway",
        "ConnectionState",
        "ConnectionStateMachine",
        "ReconnectConfig",
        "GatewayConfig",
        "GatewayType",
    ]
except ImportError:  # pragma: no cover
    pass
