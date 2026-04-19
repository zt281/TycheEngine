"""CTP gateway package — OpenCTP sim and live CTP broker gateways.

The ``openctp-ctp`` package is an **optional** dependency.  If it is not
installed the imports below will silently degrade and the names will not be
available.
"""

from typing import List

__all__: List[str] = []

try:
    from modules.trading.gateway.ctp.gateway import CtpGateway  # noqa: F401
    from modules.trading.gateway.ctp.live import CtpLiveGateway  # noqa: F401
    from modules.trading.gateway.ctp.sim import CtpSimGateway  # noqa: F401

    __all__ += ["CtpGateway", "CtpLiveGateway", "CtpSimGateway"]
except ImportError:  # pragma: no cover
    pass
