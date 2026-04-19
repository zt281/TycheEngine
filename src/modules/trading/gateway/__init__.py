"""Gateway package - Exchange/venue connectivity modules."""

# CTP gateways (optional — requires ``openctp-ctp``)
try:
    from modules.trading.gateway.ctp import (  # noqa: F401
        CtpGateway,
        CtpLiveGateway,
        CtpSimGateway,
    )
except ImportError:  # pragma: no cover
    pass
