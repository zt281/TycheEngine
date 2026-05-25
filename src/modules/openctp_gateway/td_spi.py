"""Trade Data SPI (callback handler) for OpenCTP/TTS API.

The TdSpi class inherits from the CTP TdSpi base class (via SWIG director)
and handles trade-related callbacks including instrument queries.

Usage:
    spi = TdSpi(td_module, front_addr, broker_id, user_id, password)
    spi.connect()
    spi.wait_login()
    spi.query_instruments()
    spi.wait_instruments()
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _decode(val: Any) -> str:
    """Decode CTP bytes field to string, handling None and bytes."""
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="ignore").strip("\x00")
    return str(val)


class TdSpi:
    """Trade SPI - handles trade API callbacks including instrument queries.

    Attributes:
        td_api: The CThostFtdcTraderApi instance
        connected: Whether front connection is established
        logged_in: Whether login succeeded
        instruments: List of collected instrument info dicts
    """

    def __init__(
        self,
        td_module: Any,
        front_addr: str,
        broker_id: str,
        user_id: str,
        password: str,
        on_order_callback: Optional[Callable[[dict], None]] = None,
        on_trade_callback: Optional[Callable[[dict], None]] = None,
    ):
        """Initialize TdSpi.

        Args:
            td_module: The imported CTP td API module
            front_addr: Front address (e.g. "tcp://121.37.80.177:20002")
            broker_id: Broker ID
            user_id: User ID for login
            password: Password for login
            on_order_callback: Optional callback for order updates
            on_trade_callback: Optional callback for trade updates
        """
        self._td_module = td_module
        self._front_addr = front_addr
        self._broker_id = broker_id
        self._user_id = user_id
        self._password = password
        self._on_order_callback = on_order_callback
        self._on_trade_callback = on_trade_callback

        self.td_api = None  # type: Optional[Any]
        self.connected = False
        self.logged_in = False

        # Instrument collection
        self.instruments = []  # type: List[dict]
        self._instruments_lock = threading.Lock()
        self._instrument_event = threading.Event()
        self._login_event = threading.Event()

        self._request_id = 0
        self._spi_instance = None  # type: Optional[Any]

    def _next_request_id(self) -> int:
        """Get next request ID (thread-safe increment)."""
        self._request_id += 1
        return self._request_id

    def connect(self) -> None:
        """Create API instance, register SPI, and initiate connection."""
        spi_cls = self._create_spi_class()
        self._spi_instance = spi_cls(self)

        self.td_api = self._td_module.CThostFtdcTraderApi.CreateFtdcTraderApi("")
        self.td_api.RegisterSpi(self._spi_instance)
        self.td_api.RegisterFront(self._front_addr)

        # Subscribe private stream from start
        self.td_api.SubscribePublicTopic(self._td_module.THOST_TERT_QUICK)
        self.td_api.SubscribePrivateTopic(self._td_module.THOST_TERT_QUICK)

        logger.info("TdApi connecting to %s", self._front_addr)
        self.td_api.Init()

    def wait_login(self, timeout: float = 10.0) -> bool:
        """Wait for login to complete.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if login succeeded within timeout
        """
        return self._login_event.wait(timeout)

    def query_instruments(self, exchange_id: str = "") -> None:
        """Send instrument query request.

        Args:
            exchange_id: Optional exchange filter (empty = all)
        """
        if not self.td_api or not self.logged_in:
            logger.warning("Cannot query instruments: not logged in")
            return

        self._instrument_event.clear()
        with self._instruments_lock:
            self.instruments.clear()

        req = self._td_module.CThostFtdcQryInstrumentField()
        if exchange_id:
            req.ExchangeID = exchange_id

        ret = self.td_api.ReqQryInstrument(req, self._next_request_id())
        logger.info("ReqQryInstrument sent, ret=%d", ret)

    def wait_instruments(self, timeout: float = 30.0) -> bool:
        """Wait for instrument query to complete.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if query completed within timeout
        """
        return self._instrument_event.wait(timeout)

    def release(self) -> None:
        """Release the API instance."""
        if self.td_api is not None:
            try:
                self.td_api.RegisterSpi(None)
                self.td_api.Release()
            except Exception as e:
                logger.debug("TdApi release error: %s", e)
            self.td_api = None
        self._spi_instance = None

    def _create_spi_class(self) -> type:
        """Dynamically create a SPI class that inherits from the correct CTP base."""
        td_module = self._td_module
        base_class = td_module.CThostFtdcTraderSpi
        outer = self

        class _InnerTdSpi(base_class):
            """Inner SPI class with SWIG director inheritance."""

            def __init__(self, parent: "TdSpi"):
                super().__init__()  # CRITICAL: SWIG director init
                self._parent = parent

            def OnFrontConnected(self):
                logger.info("TdSpi: Front connected")
                self._parent.connected = True
                # Send login request
                req = td_module.CThostFtdcReqUserLoginField()
                req.BrokerID = outer._broker_id
                req.UserID = outer._user_id
                req.Password = outer._password
                self._parent.td_api.ReqUserLogin(req, outer._next_request_id())

            def OnFrontDisconnected(self, nReason):
                logger.warning("TdSpi: Front disconnected, reason=%d", nReason)
                self._parent.connected = False
                self._parent.logged_in = False

            def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
                if pRspInfo and pRspInfo.ErrorID != 0:
                    error_msg = _decode(pRspInfo.ErrorMsg)
                    logger.error(
                        "TdSpi: Login failed, ErrorID=%d, ErrorMsg=%s",
                        pRspInfo.ErrorID, error_msg,
                    )
                    return
                logger.info("TdSpi: Login successful")
                self._parent.logged_in = True
                self._parent._login_event.set()

            def OnRspQryInstrument(self, pInstrument, pRspInfo, nRequestID, bIsLast):
                if pRspInfo and pRspInfo.ErrorID != 0:
                    logger.error(
                        "TdSpi: QryInstrument error, ErrorID=%d, Msg=%s",
                        pRspInfo.ErrorID, _decode(pRspInfo.ErrorMsg),
                    )
                    if bIsLast:
                        self._parent._instrument_event.set()
                    return

                if pInstrument is not None:
                    info = {
                        "instrument_id": _decode(pInstrument.InstrumentID),
                        "exchange_id": _decode(pInstrument.ExchangeID),
                        "instrument_name": _decode(pInstrument.InstrumentName),
                        "product_id": _decode(pInstrument.ProductID),
                        "product_class": _decode(pInstrument.ProductClass),
                        "volume_multiple": pInstrument.VolumeMultiple,
                        "price_tick": pInstrument.PriceTick,
                        "expire_date": _decode(pInstrument.ExpireDate),
                        "underlying_instr_id": _decode(pInstrument.UnderlyingInstrID),
                        "strike_price": pInstrument.StrikePrice,
                    }
                    with self._parent._instruments_lock:
                        self._parent.instruments.append(info)

                if bIsLast:
                    count = len(self._parent.instruments)
                    logger.info("TdSpi: Instrument query complete, total=%d", count)
                    self._parent._instrument_event.set()

            def OnRtnOrder(self, pOrder):
                if pOrder is None:
                    return
                if self._parent._on_order_callback is None:
                    return
                try:
                    order_data = {
                        "instrument_id": _decode(pOrder.InstrumentID),
                        "exchange_id": _decode(pOrder.ExchangeID),
                        "order_ref": _decode(pOrder.OrderRef),
                        "direction": _decode(pOrder.Direction),
                        "offset_flag": _decode(pOrder.CombOffsetFlag),
                        "limit_price": pOrder.LimitPrice,
                        "volume": pOrder.VolumeTotalOriginal,
                        "volume_traded": pOrder.VolumeTraded,
                        "status": _decode(pOrder.OrderStatus),
                        "status_msg": _decode(pOrder.StatusMsg),
                        "order_sys_id": _decode(pOrder.OrderSysID),
                    }
                    self._parent._on_order_callback(order_data)
                except Exception as e:
                    logger.error("TdSpi: Error parsing order: %s", e)

            def OnRtnTrade(self, pTrade):
                if pTrade is None:
                    return
                if self._parent._on_trade_callback is None:
                    return
                try:
                    trade_data = {
                        "instrument_id": _decode(pTrade.InstrumentID),
                        "exchange_id": _decode(pTrade.ExchangeID),
                        "trade_id": _decode(pTrade.TradeID),
                        "order_ref": _decode(pTrade.OrderRef),
                        "direction": _decode(pTrade.Direction),
                        "offset_flag": _decode(pTrade.OffsetFlag),
                        "price": pTrade.Price,
                        "volume": pTrade.Volume,
                        "trade_time": _decode(pTrade.TradeTime),
                    }
                    self._parent._on_trade_callback(trade_data)
                except Exception as e:
                    logger.error("TdSpi: Error parsing trade: %s", e)

            def OnRspError(self, pRspInfo, nRequestID, bIsLast):
                if pRspInfo:
                    logger.error(
                        "TdSpi: RspError ErrorID=%d, ErrorMsg=%s",
                        pRspInfo.ErrorID, _decode(pRspInfo.ErrorMsg),
                    )

        return _InnerTdSpi
