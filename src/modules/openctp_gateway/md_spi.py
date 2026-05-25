"""Market Data SPI (callback handler) for OpenCTP/TTS API.

The MdSpi class inherits from the CTP MdSpi base class (via SWIG director)
and receives market data callbacks from the CTP API internal thread.

Usage:
    # md_module is either thostmduserapi or soptthostmduserapi
    spi = MdSpi(md_module, on_data_callback, front_addr, broker_id, user_id, password)
    spi.connect()
"""

import logging
import threading
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


def _decode(val: Any) -> str:
    """Decode CTP bytes field to string, handling None and bytes."""
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="ignore").strip("\x00")
    return str(val)


class MdSpi:
    """Market Data SPI - receives quotes from CTP/TTS market data API.

    This class dynamically inherits from the correct CTP SPI base class
    depending on whether futures or stocks API is loaded.

    Attributes:
        md_api: The CThostFtdcMdApi instance
        connected: Whether front connection is established
        logged_in: Whether login succeeded
    """

    def __init__(
        self,
        md_module: Any,
        on_data_callback: Callable[[dict], None],
        front_addr: str,
        broker_id: str,
        user_id: str,
        password: str,
    ):
        """Initialize MdSpi.

        Args:
            md_module: The imported CTP md API module (thostmduserapi or soptthostmduserapi)
            on_data_callback: Callback invoked with parsed market data dict
            front_addr: Front address (e.g. "tcp://121.37.80.177:20004")
            broker_id: Broker ID
            user_id: User ID for login
            password: Password for login
        """
        self._md_module = md_module
        self._on_data_callback = on_data_callback
        self._front_addr = front_addr
        self._broker_id = broker_id
        self._user_id = user_id
        self._password = password

        self.md_api = None  # type: Optional[Any]
        self.connected = False
        self.logged_in = False
        self._login_event = threading.Event()
        self._spi_instance = None  # type: Optional[Any]

    def connect(self) -> None:
        """Create API instance, register SPI, and initiate connection."""
        # Create the inner SPI class that inherits from CTP base
        spi_cls = self._create_spi_class()
        self._spi_instance = spi_cls(self)

        # Create API and register
        self.md_api = self._md_module.CThostFtdcMdApi.CreateFtdcMdApi("")
        self.md_api.RegisterSpi(self._spi_instance)
        self.md_api.RegisterFront(self._front_addr)

        logger.info("MdApi connecting to %s", self._front_addr)
        self.md_api.Init()

    def wait_login(self, timeout: float = 10.0) -> bool:
        """Wait for login to complete.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if login succeeded within timeout
        """
        return self._login_event.wait(timeout)

    def subscribe(self, instrument_ids: List[str]) -> None:
        """Subscribe to market data for given instrument IDs.

        Args:
            instrument_ids: List of instrument IDs (e.g. ["ag2506", "au2506"])
        """
        if not self.md_api or not self.logged_in:
            logger.warning("Cannot subscribe: not logged in")
            return

        if not instrument_ids:
            return

        # CTP API expects bytes list
        ids_bytes = [iid.encode("utf-8") for iid in instrument_ids]
        ret = self.md_api.SubscribeMarketData(ids_bytes, len(ids_bytes))
        logger.info(
            "SubscribeMarketData: %d instruments, ret=%d",
            len(ids_bytes), ret,
        )

    def release(self) -> None:
        """Release the API instance."""
        if self.md_api is not None:
            try:
                self.md_api.RegisterSpi(None)
                self.md_api.Release()
            except Exception as e:
                logger.debug("MdApi release error: %s", e)
            self.md_api = None
        self._spi_instance = None

    def _create_spi_class(self) -> type:
        """Dynamically create a SPI class that inherits from the correct CTP base."""
        md_module = self._md_module
        base_class = md_module.CThostFtdcMdSpi
        outer = self

        class _InnerMdSpi(base_class):
            """Inner SPI class with SWIG director inheritance."""

            def __init__(self, parent: "MdSpi"):
                super().__init__()  # CRITICAL: SWIG director init
                self._parent = parent

            def OnFrontConnected(self):
                logger.info("MdSpi: Front connected")
                self._parent.connected = True
                # Send login request
                req = md_module.CThostFtdcReqUserLoginField()
                req.BrokerID = outer._broker_id
                req.UserID = outer._user_id
                req.Password = outer._password
                self._parent.md_api.ReqUserLogin(req, 0)

            def OnFrontDisconnected(self, nReason):
                logger.warning("MdSpi: Front disconnected, reason=%d", nReason)
                self._parent.connected = False
                self._parent.logged_in = False

            def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
                if pRspInfo and pRspInfo.ErrorID != 0:
                    error_msg = _decode(pRspInfo.ErrorMsg)
                    logger.error(
                        "MdSpi: Login failed, ErrorID=%d, ErrorMsg=%s",
                        pRspInfo.ErrorID, error_msg,
                    )
                    return
                logger.info("MdSpi: Login successful")
                self._parent.logged_in = True
                self._parent._login_event.set()

            def OnRspSubMarketData(self, pSpecificInstrument, pRspInfo, nRequestID, bIsLast):
                if pRspInfo and pRspInfo.ErrorID != 0:
                    instrument = _decode(pSpecificInstrument.InstrumentID) if pSpecificInstrument else "?"
                    error_msg = _decode(pRspInfo.ErrorMsg)
                    logger.warning(
                        "MdSpi: Subscribe failed for %s, ErrorID=%d, Msg=%s",
                        instrument, pRspInfo.ErrorID, error_msg,
                    )

            def OnRtnDepthMarketData(self, pDepthMarketData):
                if pDepthMarketData is None:
                    return
                try:
                    data = self._parse_market_data(pDepthMarketData)
                    self._parent._on_data_callback(data)
                except Exception as e:
                    logger.error("MdSpi: Error parsing market data: %s", e)

            def OnRspError(self, pRspInfo, nRequestID, bIsLast):
                if pRspInfo:
                    logger.error(
                        "MdSpi: RspError ErrorID=%d, ErrorMsg=%s",
                        pRspInfo.ErrorID, _decode(pRspInfo.ErrorMsg),
                    )

            @staticmethod
            def _parse_market_data(data) -> dict:
                """Parse CThostFtdcDepthMarketDataField to dict."""
                return {
                    "instrument_id": _decode(data.InstrumentID),
                    "exchange_id": _decode(data.ExchangeID),
                    "last_price": data.LastPrice,
                    "pre_settlement_price": data.PreSettlementPrice,
                    "pre_close_price": data.PreClosePrice,
                    "open_price": data.OpenPrice,
                    "highest_price": data.HighestPrice,
                    "lowest_price": data.LowestPrice,
                    "volume": data.Volume,
                    "turnover": data.Turnover,
                    "open_interest": data.OpenInterest,
                    "close_price": data.ClosePrice,
                    "settlement_price": data.SettlementPrice,
                    "upper_limit_price": data.UpperLimitPrice,
                    "lower_limit_price": data.LowerLimitPrice,
                    "bid_price1": data.BidPrice1,
                    "bid_volume1": data.BidVolume1,
                    "ask_price1": data.AskPrice1,
                    "ask_volume1": data.AskVolume1,
                    "update_time": _decode(data.UpdateTime),
                    "update_millisec": data.UpdateMillisec,
                    "trading_day": _decode(data.TradingDay),
                    "action_day": _decode(data.ActionDay),
                }

        return _InnerMdSpi
