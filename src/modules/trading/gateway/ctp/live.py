"""Live CTP broker gateway (实盘).

Connects to a real CTP broker frontend.  Typically requires ``auth_code``
and ``app_id`` for the authentication handshake mandated by the broker.
"""

from typing import Any, Optional

from modules.trading.gateway.ctp.gateway import CtpGateway
from tyche.types import Endpoint


class CtpLiveGateway(CtpGateway):
    """Live CTP broker gateway.

    All connection parameters must be supplied explicitly — there are no
    built-in defaults because every broker has its own front addresses.

    Args:
        engine_endpoint: ZMQ endpoint of the TycheEngine broker.
        broker_id: CTP broker ID assigned by the futures company.
        user_id: Trading account user ID.
        password: Trading account password.
        td_front: Trading front address (e.g. ``"tcp://180.168.146.187:10201"``).
        md_front: Market-data front address.
        auth_code: Broker-issued authentication code (required for most live brokers).
        app_id: Application ID registered with the broker.
        venue_name: Venue identifier used in instrument IDs (default ``"ctp"``).
        module_id: Optional TycheModule ID override.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        broker_id: str,
        user_id: str,
        password: str,
        td_front: str,
        md_front: str,
        auth_code: Optional[str] = None,
        app_id: Optional[str] = None,
        venue_name: str = "ctp",
        module_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            engine_endpoint=engine_endpoint,
            venue_name=venue_name,
            broker_id=broker_id,
            user_id=user_id,
            password=password,
            td_front=td_front,
            md_front=md_front,
            auth_code=auth_code,
            app_id=app_id,
            require_auth=bool(auth_code and app_id),
            module_id=module_id,
            **kwargs,
        )
