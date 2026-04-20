"""Shared CTP gateway base class bridging CTP async SPI callbacks with TycheEngine events.

Uses openctp-ctp to connect to CTP-compatible trading frontends (both simulated
via OpenCTP and live brokers). CTP SPI callbacks arrive on CTP's internal threads;
a ``queue.Queue`` bridges them into the module's event dispatcher thread which then
publishes via TycheEngine's ZMQ event system.
"""

import logging
import os
import queue
import re
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from openctp_ctp import mdapi, tdapi

from modules.trading.gateway.base import GatewayModule
from modules.trading.gateway.ctp.state_machine import (
    ConnectionState,
    ConnectionStateMachine,
    ReconnectConfig,
)
from modules.trading.models.account import Account, Balance
from modules.trading.models.enums import OrderStatus, OrderType, PositionSide, Side, TimeInForce
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.models.position import Position
from modules.trading.models.tick import Quote, Trade
from tyche.types import Endpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CTP exchange mapping: instrument prefix -> exchange ID
# ---------------------------------------------------------------------------

EXCHANGE_MAP: Dict[str, str] = {
    # CFFEX (中国金融期货交易所) - Index futures and bond futures
    "IF": "CFFEX", "IC": "CFFEX", "IH": "CFFEX", "IM": "CFFEX",
    "T": "CFFEX", "TF": "CFFEX", "TS": "CFFEX", "TL": "CFFEX",
    # SHFE (上海期货交易所)
    "cu": "SHFE", "al": "SHFE", "zn": "SHFE", "pb": "SHFE",
    "ni": "SHFE", "sn": "SHFE", "au": "SHFE", "ag": "SHFE",
    "rb": "SHFE", "wr": "SHFE", "hc": "SHFE", "ss": "SHFE",
    "fu": "SHFE", "bu": "SHFE", "ru": "SHFE", "sp": "SHFE",
    "ao": "SHFE", "br": "SHFE",
    # DCE (大连商品交易所)
    "c": "DCE", "cs": "DCE", "a": "DCE", "b": "DCE",
    "m": "DCE", "y": "DCE", "p": "DCE", "fb": "DCE",
    "bb": "DCE", "jd": "DCE", "rr": "DCE", "lh": "DCE",
    "l": "DCE", "v": "DCE", "pp": "DCE", "j": "DCE",
    "jm": "DCE", "i": "DCE", "eg": "DCE", "eb": "DCE",
    "pg": "DCE",
    # CZCE (郑州商品交易所)
    "CF": "CZCE", "CY": "CZCE", "SR": "CZCE", "TA": "CZCE",
    "OI": "CZCE", "RI": "CZCE", "MA": "CZCE", "FG": "CZCE",
    "SF": "CZCE", "SM": "CZCE", "AP": "CZCE", "CJ": "CZCE",
    "UR": "CZCE", "SA": "CZCE", "PF": "CZCE", "PK": "CZCE",
    "SH": "CZCE", "PX": "CZCE",
    # INE (上海国际能源交易中心)
    "sc": "INE", "lu": "INE", "nr": "INE", "bc": "INE", "ec": "INE",
    # GFEX (广州期货交易所)
    "si": "GFEX", "lc": "GFEX",
}

# CTP OrderStatus -> TycheEngine OrderStatus
CTP_STATUS_MAP: Dict[str, OrderStatus] = {
    "0": OrderStatus.FILLED,               # THOST_FTDC_OST_AllTraded
    "1": OrderStatus.PARTIALLY_FILLED,      # THOST_FTDC_OST_PartTradedQueueing
    "2": OrderStatus.PARTIALLY_FILLED,      # THOST_FTDC_OST_PartTradedNotQueueing
    "3": OrderStatus.SUBMITTED,             # THOST_FTDC_OST_NoTradeQueueing
    "4": OrderStatus.SUBMITTED,             # THOST_FTDC_OST_NoTradeNotQueueing
    "5": OrderStatus.CANCELLED,             # THOST_FTDC_OST_Canceled
    "a": OrderStatus.PENDING_SUBMIT,        # THOST_FTDC_OST_Unknown
    "b": OrderStatus.NEW,                   # THOST_FTDC_OST_NotTouched
    "c": OrderStatus.SUBMITTED,             # THOST_FTDC_OST_Touched
}

# Regex to extract alphabetic prefix from CTP instrument ID (e.g. "rb2410" -> "rb")
_PREFIX_RE = re.compile(r"^([a-zA-Z]+)")


def _infer_exchange(ctp_symbol: str) -> str:
    """Infer exchange ID from a CTP instrument symbol."""
    m = _PREFIX_RE.match(ctp_symbol)
    if m:
        prefix = m.group(1)
        # Try exact match first (handles multi-char prefixes like "jm", "pp")
        # Sort by length descending so longer prefixes match first
        for length in (len(prefix), len(prefix) - 1, 1):
            candidate = prefix[:length]
            if candidate in EXCHANGE_MAP:
                return EXCHANGE_MAP[candidate]
    return "UNKNOWN"


def _extract_symbol(instrument_id: str) -> str:
    """Extract the CTP symbol from a TycheEngine instrument_id (``symbol.venue.asset_class``)."""
    return instrument_id.split(".")[0]


def _to_instrument_id(ctp_symbol: str, venue_name: str) -> str:
    """Build a TycheEngine instrument_id string from a CTP symbol."""
    return f"{ctp_symbol}.{venue_name}.futures"


def _safe_str(value: Any) -> str:
    """Decode bytes to str if needed, stripping null padding."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00")
    return str(value).strip("\x00") if value is not None else ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert CTP numeric field to float safely, treating max-double as zero."""
    try:
        f = float(value)
        # CTP uses DBL_MAX (~1.7e308) for undefined/empty price fields
        if f > 1e300 or f < -1e300:
            return default
        return f
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# CtpGateway
# ---------------------------------------------------------------------------


class CtpGateway(GatewayModule):
    """Base CTP gateway bridging CTP SPI callbacks with TycheEngine events.

    Subclass as :class:`CtpSimGateway` (OpenCTP) or :class:`CtpLiveGateway`
    (real broker) — they only differ in default addresses / auth requirements.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        venue_name: str,
        broker_id: str,
        user_id: str,
        password: str,
        td_front: str,
        md_front: str,
        auth_code: Optional[str] = None,
        app_id: Optional[str] = None,
        require_auth: bool = False,
        flow_path: str = "./ctp_flow",
        module_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            engine_endpoint=engine_endpoint,
            venue_name=venue_name,
            module_id=module_id,
            **kwargs,
        )
        self._broker_id = broker_id
        self._user_id = user_id
        self._password = password
        self._td_front = td_front
        self._md_front = md_front
        self._auth_code = auth_code or ""
        self._app_id = app_id or ""
        self._require_auth = require_auth
        self._flow_path = flow_path

        # CTP API handles (created in connect())
        self._md_api: Optional[mdapi.CThostFtdcMdApi] = None
        self._td_api: Optional[tdapi.CThostFtdcTraderApi] = None

        # Thread synchronization
        self._md_login_event = threading.Event()
        self._td_login_event = threading.Event()
        self._account_event = threading.Event()

        # SPI -> module thread bridge
        self._event_queue: queue.Queue[Tuple[str, Any]] = queue.Queue()
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._dispatcher_stop = threading.Event()

        # Order ref management
        self._order_ref_counter = 0
        self._order_ref_lock = threading.Lock()
        self._order_ref_map: Dict[str, str] = {}     # order_ref -> order_id
        self._order_id_map: Dict[str, str] = {}      # order_id -> order_ref
        self._order_sys_map: Dict[str, Dict[str, str]] = {}  # order_id -> {OrderSysID, ExchangeID, ...}

        # Account query result cache
        self._account_cache: Optional[Dict[str, Any]] = None

        # Last price cache for trade generation from market data
        self._last_prices: Dict[str, float] = {}

        # Last cumulative volume cache for computing per-tick trade size
        self._last_volumes: Dict[str, float] = {}

        # Connection state machine
        self.state_machine = ConnectionStateMachine(
            venue=venue_name,
            reconnect_config=ReconnectConfig(),
        )

        # Position accumulator for OnRspQryInvestorPosition
        self._position_accumulator: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Order ref helpers
    # ------------------------------------------------------------------

    def _next_order_ref(self) -> str:
        with self._order_ref_lock:
            self._order_ref_counter += 1
            return str(self._order_ref_counter)

    # ------------------------------------------------------------------
    # Inner SPI classes
    # ------------------------------------------------------------------

    class _MdSpi(mdapi.CThostFtdcMdSpi):
        """Market data SPI — callbacks run on CTP's internal thread."""

        def __init__(self, gateway: "CtpGateway") -> None:
            super().__init__()
            self._gw = gateway

        def OnFrontConnected(self) -> None:  # noqa: N802
            logger.info("[MD] Front connected, logging in …")
            req = mdapi.CThostFtdcReqUserLoginField()
            req.BrokerID = self._gw._broker_id
            req.UserID = self._gw._user_id
            req.Password = self._gw._password
            self._gw._md_api.ReqUserLogin(req, 0)  # type: ignore[union-attr]

        def OnFrontDisconnected(self, nReason: int) -> None:  # noqa: N802,N803
            logger.warning("[MD] Front disconnected, reason=%d", nReason)

        def OnRspUserLogin(  # noqa: N802
            self,
            pRspUserLogin: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.error(
                    "[MD] Login failed: [%d] %s",
                    pRspInfo.ErrorID,
                    _safe_str(pRspInfo.ErrorMsg),
                )
                return
            logger.info("[MD] Login succeeded")
            self._gw._md_login_event.set()

        def OnRspSubMarketData(  # noqa: N802
            self,
            pSpecificInstrument: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.warning(
                    "[MD] Subscribe failed for %s: [%d] %s",
                    _safe_str(getattr(pSpecificInstrument, "InstrumentID", "?")),
                    pRspInfo.ErrorID,
                    _safe_str(pRspInfo.ErrorMsg),
                )
            else:
                logger.info(
                    "[MD] Subscribed: %s",
                    _safe_str(getattr(pSpecificInstrument, "InstrumentID", "?")),
                )

        def OnRtnDepthMarketData(  # noqa: N802
            self,
            pDepthMarketData: Any,  # noqa: N803
        ) -> None:
            if pDepthMarketData is None:
                return
            ctp_symbol = _safe_str(pDepthMarketData.InstrumentID)
            instrument_id = _to_instrument_id(ctp_symbol, self._gw.venue_name)
            now = time.time()

            bid = _safe_float(pDepthMarketData.BidPrice1)
            ask = _safe_float(pDepthMarketData.AskPrice1)
            bid_size = _safe_float(pDepthMarketData.BidVolume1)
            ask_size = _safe_float(pDepthMarketData.AskVolume1)
            last_price = _safe_float(pDepthMarketData.LastPrice)

            if bid <= 0 and ask <= 0:
                return  # No valid quote

            quote = Quote(
                instrument_id=instrument_id,
                bid=Decimal(str(bid)) if bid > 0 else Decimal("0"),
                ask=Decimal(str(ask)) if ask > 0 else Decimal("0"),
                bid_size=Decimal(str(int(bid_size))),
                ask_size=Decimal(str(int(ask_size))),
                timestamp=now,
            )
            self._gw._event_queue.put(("quote", quote))

            # Generate Trade event from volume delta
            current_volume = _safe_float(pDepthMarketData.Volume)
            prev_volume = self._gw._last_volumes.get(ctp_symbol, 0.0)
            prev_price = self._gw._last_prices.get(ctp_symbol)
            self._gw._last_volumes[ctp_symbol] = current_volume

            if last_price > 0:
                self._gw._last_prices[ctp_symbol] = last_price
                volume_delta = current_volume - prev_volume
                if volume_delta > 0:
                    trade = Trade(
                        instrument_id=instrument_id,
                        price=Decimal(str(last_price)),
                        size=Decimal(str(int(volume_delta))),
                        side=Side.BUY if prev_price is not None and last_price >= prev_price else Side.SELL,
                        timestamp=now,
                        trade_id=f"ctp-{ctp_symbol}-{int(now * 1000)}",
                    )
                    self._gw._event_queue.put(("trade", trade))

    class _TdSpi(tdapi.CThostFtdcTraderSpi):
        """Trader SPI — callbacks run on CTP's internal thread."""

        def __init__(self, gateway: "CtpGateway") -> None:
            super().__init__()
            self._gw = gateway

        def OnFrontConnected(self) -> None:  # noqa: N802
            logger.info("[TD] Front connected")
            if self._gw._require_auth:
                logger.info("[TD] Authenticating …")
                req = tdapi.CThostFtdcReqAuthenticateField()
                req.BrokerID = self._gw._broker_id
                req.UserID = self._gw._user_id
                req.AuthCode = self._gw._auth_code
                req.AppID = self._gw._app_id
                self._gw._td_api.ReqAuthenticate(req, 0)  # type: ignore[union-attr]
            else:
                self._login()

        def OnFrontDisconnected(self, nReason: int) -> None:  # noqa: N802,N803
            logger.warning("[TD] Front disconnected, reason=%d", nReason)

        def OnRspAuthenticate(  # noqa: N802
            self,
            pRspAuthenticateField: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.error(
                    "[TD] Auth failed: [%d] %s",
                    pRspInfo.ErrorID,
                    _safe_str(pRspInfo.ErrorMsg),
                )
                return
            logger.info("[TD] Auth succeeded, logging in …")
            self._login()

        def _login(self) -> None:
            req = tdapi.CThostFtdcReqUserLoginField()
            req.BrokerID = self._gw._broker_id
            req.UserID = self._gw._user_id
            req.Password = self._gw._password
            self._gw._td_api.ReqUserLogin(req, 0)  # type: ignore[union-attr]

        def OnRspUserLogin(  # noqa: N802
            self,
            pRspUserLogin: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.error(
                    "[TD] Login failed: [%d] %s",
                    pRspInfo.ErrorID,
                    _safe_str(pRspInfo.ErrorMsg),
                )
                return
            logger.info("[TD] Login succeeded (FrontID=%s, SessionID=%s)",
                        getattr(pRspUserLogin, "FrontID", "?"),
                        getattr(pRspUserLogin, "SessionID", "?"))
            # Seed the order ref counter from the max order ref returned by CTP
            max_ref = _safe_str(getattr(pRspUserLogin, "MaxOrderRef", "0"))
            try:
                self._gw._order_ref_counter = int(max_ref)
            except ValueError:
                pass
            self._gw._td_login_event.set()

        # --- Order responses ---

        def OnRspOrderInsert(  # noqa: N802
            self,
            pInputOrder: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                order_ref = _safe_str(getattr(pInputOrder, "OrderRef", ""))
                order_id = self._gw._order_ref_map.get(order_ref, order_ref)
                instrument_id_raw = _safe_str(getattr(pInputOrder, "InstrumentID", ""))
                instrument_id = _to_instrument_id(instrument_id_raw, self._gw.venue_name)
                reason = _safe_str(pRspInfo.ErrorMsg)
                logger.error("[TD] OrderInsert rejected ref=%s: [%d] %s",
                             order_ref, pRspInfo.ErrorID, reason)
                update = OrderUpdate(
                    order_id=order_id,
                    instrument_id=instrument_id,
                    status=OrderStatus.REJECTED,
                    timestamp=time.time(),
                    reason=reason,
                )
                self._gw._event_queue.put(("order_update", update))

        def OnRtnOrder(  # noqa: N802
            self,
            pOrder: Any,  # noqa: N803
        ) -> None:
            if pOrder is None:
                return
            order_ref = _safe_str(pOrder.OrderRef)
            order_id = self._gw._order_ref_map.get(order_ref, order_ref)
            ctp_symbol = _safe_str(pOrder.InstrumentID)
            instrument_id = _to_instrument_id(ctp_symbol, self._gw.venue_name)
            status_char = _safe_str(pOrder.OrderStatus)
            status = CTP_STATUS_MAP.get(status_char, OrderStatus.PENDING_SUBMIT)

            # Cache exchange-level info for cancel
            order_sys_id = _safe_str(pOrder.OrderSysID)
            exchange_id = _safe_str(pOrder.ExchangeID)
            if order_sys_id:
                self._gw._order_sys_map[order_id] = {
                    "OrderSysID": order_sys_id,
                    "ExchangeID": exchange_id,
                    "FrontID": str(getattr(pOrder, "FrontID", "")),
                    "SessionID": str(getattr(pOrder, "SessionID", "")),
                    "OrderRef": order_ref,
                }

            filled_qty = _safe_float(pOrder.VolumeTraded)
            avg_price = _safe_float(getattr(pOrder, "AveragePrice", 0.0))
            if avg_price <= 0:
                avg_price = _safe_float(pOrder.LimitPrice)

            reason: Optional[str] = None
            if status == OrderStatus.CANCELLED:
                reason = _safe_str(getattr(pOrder, "StatusMsg", ""))

            update = OrderUpdate(
                order_id=order_id,
                instrument_id=instrument_id,
                status=status,
                filled_quantity=Decimal(str(int(filled_qty))),
                avg_fill_price=Decimal(str(avg_price)) if avg_price > 0 else None,
                timestamp=time.time(),
                reason=reason,
            )
            self._gw._event_queue.put(("order_update", update))

        def OnRtnTrade(  # noqa: N802
            self,
            pTrade: Any,  # noqa: N803
        ) -> None:
            if pTrade is None:
                return
            order_ref = _safe_str(pTrade.OrderRef)
            order_id = self._gw._order_ref_map.get(order_ref, order_ref)
            ctp_symbol = _safe_str(pTrade.InstrumentID)
            instrument_id = _to_instrument_id(ctp_symbol, self._gw.venue_name)
            direction = _safe_str(pTrade.Direction)
            side = Side.BUY if direction == "0" else Side.SELL
            price = _safe_float(pTrade.Price)
            volume = _safe_float(pTrade.Volume)
            trade_id = _safe_str(pTrade.TradeID)

            fill = Fill(
                order_id=order_id,
                instrument_id=instrument_id,
                side=side,
                price=Decimal(str(price)),
                quantity=Decimal(str(int(volume))),
                timestamp=time.time(),
                venue_fill_id=trade_id,
            )
            self._gw._event_queue.put(("fill", fill))

        # --- Account query ---

        def OnRspQryTradingAccount(  # noqa: N802
            self,
            pTradingAccount: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.error("[TD] QryTradingAccount error: [%d] %s",
                             pRspInfo.ErrorID, _safe_str(pRspInfo.ErrorMsg))
                self._gw._account_event.set()
                return
            if pTradingAccount is None:
                self._gw._account_event.set()
                return
            equity = _safe_float(pTradingAccount.Balance)
            available = _safe_float(pTradingAccount.Available)
            margin = _safe_float(pTradingAccount.CurrMargin)
            frozen = _safe_float(pTradingAccount.FrozenMargin)
            close_pnl = _safe_float(pTradingAccount.CloseProfit)
            position_pnl = _safe_float(pTradingAccount.PositionProfit)
            currency = _safe_str(pTradingAccount.CurrencyID) or "CNY"

            account = Account(
                account_id=self._gw._user_id,
                venue=self._gw.venue_name,
                balances=[
                    Balance(
                        currency=currency,
                        total=Decimal(str(equity)),
                        available=Decimal(str(available)),
                        frozen=Decimal(str(frozen)),
                    ),
                ],
                total_equity=Decimal(str(equity)),
                margin_used=Decimal(str(margin)),
                margin_available=Decimal(str(available)),
                unrealized_pnl=Decimal(str(position_pnl)),
                realized_pnl=Decimal(str(close_pnl)),
                timestamp=time.time(),
            )
            self._gw._account_cache = account.to_dict()
            if bIsLast:
                self._gw._account_event.set()

        def OnRspError(
            self,
            pRspInfo: Any,
            nRequestID: int,
            bIsLast: bool,
        ) -> None:
            if pRspInfo is None:
                return
            error_id = getattr(pRspInfo, "ErrorID", 0)
            error_msg = _safe_str(getattr(pRspInfo, "ErrorMsg", ""))
            if error_id != 0:
                logger.error("[TD] RspError: [%d] %s", error_id, error_msg)
                self._gw._publish_error(
                    error_id=error_id,
                    error_msg=error_msg,
                    source="td_api",
                    context=f"request_id={nRequestID}",
                )

        def OnRspQryInvestorPosition(  # noqa: N802
            self,
            pInvestorPosition: Any,  # noqa: N803
            pRspInfo: Any,  # noqa: N803
            nRequestID: int,  # noqa: N803
            bIsLast: bool,  # noqa: N803
        ) -> None:
            if pRspInfo and pRspInfo.ErrorID != 0:
                logger.error("[TD] QryPosition error: [%d] %s",
                             pRspInfo.ErrorID, _safe_str(pRspInfo.ErrorMsg))
                self._gw._publish_error(
                    error_id=pRspInfo.ErrorID,
                    error_msg=_safe_str(pRspInfo.ErrorMsg),
                    source="td_api",
                    context="ReqQryInvestorPosition",
                )
                return
            if pInvestorPosition is None:
                return

            ctp_symbol = _safe_str(pInvestorPosition.InstrumentID)
            instrument_id = _to_instrument_id(ctp_symbol, self._gw.venue_name)
            direction = _safe_str(pInvestorPosition.PosiDirection)
            position_qty = getattr(pInvestorPosition, "Position", 0)
            open_cost = _safe_float(getattr(pInvestorPosition, "OpenCost", 0.0))

            logger.debug(
                "[TD] Position record: %s dir=%s vol=%s",
                ctp_symbol, direction, position_qty,
            )

            if instrument_id not in self._gw._position_accumulator:
                self._gw._position_accumulator[instrument_id] = {
                    "quantity": Decimal("0"),
                    "cost": Decimal("0"),
                    "direction": direction,
                }

            acc = self._gw._position_accumulator[instrument_id]
            acc["quantity"] += Decimal(str(int(position_qty)))
            acc["cost"] += Decimal(str(open_cost))

            if bIsLast:
                qty = acc["quantity"]
                if qty > 0:
                    if direction == "1":
                        side = PositionSide.LONG
                    elif direction == "3":
                        side = PositionSide.SHORT
                    else:
                        side = PositionSide.LONG
                    avg_price = acc["cost"] / qty if qty else Decimal("0")
                else:
                    side = PositionSide.FLAT
                    avg_price = Decimal("0")

                position = Position(
                    instrument_id=instrument_id,
                    side=side,
                    quantity=qty,
                    avg_entry_price=avg_price,
                )
                self._gw._event_queue.put(("position_update", position))
                del self._gw._position_accumulator[instrument_id]

    # ------------------------------------------------------------------
    # Event dispatcher (runs on its own thread)
    # ------------------------------------------------------------------

    def _event_dispatcher(self) -> None:
        """Poll the SPI event queue and publish into TycheEngine."""
        logger.info("[CTP] Event dispatcher started")
        while not self._dispatcher_stop.is_set():
            try:
                event_type, payload = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                if event_type == "quote":
                    self.publish_quote(payload)
                elif event_type == "trade":
                    self.publish_trade(payload)
                elif event_type == "fill":
                    self.publish_fill(payload)
                elif event_type == "order_update":
                    self.publish_order_update(payload)
                elif event_type == "position_update":
                    self.publish_position_update(payload)
                else:
                    logger.warning("[CTP] Unknown event type: %s", event_type)
            except Exception:
                logger.exception("[CTP] Error dispatching event %s", event_type)

        # Drain remaining events on shutdown
        while not self._event_queue.empty():
            try:
                event_type, payload = self._event_queue.get_nowait()
                if event_type == "quote":
                    self.publish_quote(payload)
                elif event_type == "trade":
                    self.publish_trade(payload)
                elif event_type == "fill":
                    self.publish_fill(payload)
                elif event_type == "order_update":
                    self.publish_order_update(payload)
                elif event_type == "position_update":
                    self.publish_position_update(payload)
            except queue.Empty:
                break
            except Exception:
                logger.exception("[CTP] Error draining event %s", event_type)

        logger.info("[CTP] Event dispatcher stopped")

    # ------------------------------------------------------------------
    # GatewayModule abstract method implementations
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Create CTP APIs, register SPIs, connect, and wait for login."""
        if not self.state_machine.transition(ConnectionState.CONNECTING):
            logger.warning("[CTP] Cannot connect from state %s", self.state_machine.state.value)
            return
        self._publish_state("connect() called")

        # Ensure flow directory exists
        md_flow = os.path.join(self._flow_path, "md")
        td_flow = os.path.join(self._flow_path, "td")
        os.makedirs(md_flow, exist_ok=True)
        os.makedirs(td_flow, exist_ok=True)

        # --- Market data API ---
        self._md_api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(md_flow + os.sep)
        md_spi = self._MdSpi(self)
        self._md_api.RegisterSpi(md_spi)
        self._md_api.RegisterFront(self._md_front)
        self._md_api.Init()
        logger.info("[CTP] MD API init, waiting for login …")

        # --- Trader API ---
        self._td_api = tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi(td_flow + os.sep)
        td_spi = self._TdSpi(self)
        self._td_api.RegisterSpi(td_spi)
        self._td_api.RegisterFront(self._td_front)
        # Subscribe topics BEFORE Init()
        self._td_api.SubscribePrivateTopic(tdapi.THOST_TERT_QUICK)
        self._td_api.SubscribePublicTopic(tdapi.THOST_TERT_QUICK)
        self._td_api.Init()
        logger.info("[CTP] TD API init, waiting for login …")

        # Wait for both logins
        md_ok = self._md_login_event.wait(timeout=30)
        td_ok = self._td_login_event.wait(timeout=30)
        if not md_ok:
            logger.error("[CTP] MD login timed out")
        if not td_ok:
            logger.error("[CTP] TD login timed out")

        # Start dispatcher thread
        self._dispatcher_stop.clear()
        self._dispatcher_thread = threading.Thread(
            target=self._event_dispatcher, daemon=True, name="ctp-event-dispatcher",
        )
        self._dispatcher_thread.start()

        self._connected = True
        self.state_machine.transition(ConnectionState.CONNECTED)
        self._publish_state("login success")
        logger.info("[CTP] Gateway connected (venue=%s)", self.venue_name)

    def disconnect(self) -> None:
        """Release CTP APIs and stop the event dispatcher."""
        self.state_machine.transition(ConnectionState.DISCONNECTED)
        self._publish_state("disconnect() called")
        self._connected = False

        # Stop dispatcher
        self._dispatcher_stop.set()
        if self._dispatcher_thread is not None:
            self._dispatcher_thread.join(timeout=5)
            self._dispatcher_thread = None

        # Release APIs
        if self._md_api is not None:
            try:
                self._md_api.Release()
            except Exception:
                logger.exception("[CTP] Error releasing MD API")
            self._md_api = None

        if self._td_api is not None:
            try:
                self._td_api.Release()
            except Exception:
                logger.exception("[CTP] Error releasing TD API")
            self._td_api = None

        # Reset login events
        self._md_login_event.clear()
        self._td_login_event.clear()

        logger.info("[CTP] Gateway disconnected")

    def subscribe_market_data(self, instrument_ids: List[str]) -> None:
        """Subscribe to CTP market data for the given TycheEngine instrument IDs."""
        if self._md_api is None:
            raise RuntimeError("MD API not connected")

        symbols: List[str] = []
        for iid in instrument_ids:
            symbol = _extract_symbol(iid)
            symbols.append(symbol)
            if iid not in self._subscribed_instruments:
                self._subscribed_instruments.append(iid)

        if symbols:
            self._md_api.SubscribeMarketData([s.encode("utf-8") for s in symbols], len(symbols))
            logger.info("[CTP] Subscribing market data: %s", symbols)

    def submit_order(self, order: Order) -> OrderUpdate:
        """Map a TycheEngine Order to CTP InputOrderField and submit."""
        if self._td_api is None:
            raise RuntimeError("TD API not connected")

        ctp_symbol = _extract_symbol(order.instrument_id)
        exchange_id = _infer_exchange(ctp_symbol)
        order_ref = self._next_order_ref()

        # Store mapping
        self._order_ref_map[order_ref] = order.order_id
        self._order_id_map[order.order_id] = order_ref

        req = tdapi.CThostFtdcInputOrderField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user_id
        req.InstrumentID = ctp_symbol
        req.ExchangeID = exchange_id
        req.OrderRef = order_ref

        # Direction
        if order.side == Side.BUY:
            req.Direction = tdapi.THOST_FTDC_D_Buy
        else:
            req.Direction = tdapi.THOST_FTDC_D_Sell

        # Price type
        if order.order_type == OrderType.LIMIT:
            req.OrderPriceType = tdapi.THOST_FTDC_OPT_LimitPrice
            req.LimitPrice = float(order.price) if order.price else 0.0
        else:
            req.OrderPriceType = tdapi.THOST_FTDC_OPT_AnyPrice
            req.LimitPrice = 0.0

        req.VolumeTotalOriginal = int(order.quantity)

        # Offset: default to Open (can be extended for close/close-today)
        req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open
        req.CombHedgeFlag = tdapi.THOST_FTDC_HF_Speculation

        # Time condition
        if order.time_in_force == TimeInForce.IOC:
            req.TimeCondition = tdapi.THOST_FTDC_TC_IOC
            req.VolumeCondition = tdapi.THOST_FTDC_VC_AV
        elif order.time_in_force == TimeInForce.FOK:
            req.TimeCondition = tdapi.THOST_FTDC_TC_IOC
            req.VolumeCondition = tdapi.THOST_FTDC_VC_CV
        else:
            # GTC / DAY -> GFD (Good For Day) in CTP
            req.TimeCondition = tdapi.THOST_FTDC_TC_GFD
            req.VolumeCondition = tdapi.THOST_FTDC_VC_AV

        req.MinVolume = 1
        req.ContingentCondition = tdapi.THOST_FTDC_CC_Immediately
        req.ForceCloseReason = tdapi.THOST_FTDC_FCC_NotForceClose
        req.IsAutoSuspend = 0

        request_id = int(order_ref)
        ret = self._td_api.ReqOrderInsert(req, request_id)
        if ret != 0:
            reason = f"CTP ReqOrderInsert error code {ret}"
            logger.error("[CTP] %s", reason)
            return OrderUpdate(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason=reason,
            )

        logger.info("[CTP] Order submitted ref=%s id=%s %s %s %s @ %s",
                     order_ref, order.order_id, order.side.name,
                     order.quantity, ctp_symbol, order.price)

        return OrderUpdate(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            status=OrderStatus.SUBMITTED,
            timestamp=time.time(),
        )

    def cancel_order(self, order_id: str, instrument_id: str) -> OrderUpdate:
        """Cancel an outstanding order via CTP."""
        if self._td_api is None:
            raise RuntimeError("TD API not connected")

        req = tdapi.CThostFtdcInputOrderActionField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user_id
        req.ActionFlag = tdapi.THOST_FTDC_AF_Delete

        # Look up exchange-level info
        sys_info = self._order_sys_map.get(order_id)
        if sys_info:
            req.OrderSysID = sys_info["OrderSysID"]
            req.ExchangeID = sys_info["ExchangeID"]
        else:
            # Fallback: use order ref
            order_ref = self._order_id_map.get(order_id, "")
            req.OrderRef = order_ref
            ctp_symbol = _extract_symbol(instrument_id)
            req.ExchangeID = _infer_exchange(ctp_symbol)
            req.InstrumentID = ctp_symbol

        request_id = int(self._next_order_ref())
        ret = self._td_api.ReqOrderAction(req, request_id)
        if ret != 0:
            reason = f"CTP ReqOrderAction error code {ret}"
            logger.error("[CTP] %s", reason)
            return OrderUpdate(
                order_id=order_id,
                instrument_id=instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason=reason,
            )

        logger.info("[CTP] Cancel requested for order_id=%s", order_id)

        return OrderUpdate(
            order_id=order_id,
            instrument_id=instrument_id,
            status=OrderStatus.PENDING_CANCEL,
            timestamp=time.time(),
        )

    def query_account(self) -> Dict[str, Any]:
        """Query CTP trading account and wait for the response."""
        if self._td_api is None:
            raise RuntimeError("TD API not connected")

        self._account_event.clear()
        self._account_cache = None

        req = tdapi.CThostFtdcQryTradingAccountField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user_id
        ret = self._td_api.ReqQryTradingAccount(req, int(self._next_order_ref()))
        if ret != 0:
            logger.error("[CTP] ReqQryTradingAccount returned %d", ret)

        if not self._account_event.wait(timeout=10):
            logger.warning("[CTP] Account query timed out")

        return self._account_cache or {
            "venue": self.venue_name,
            "error": "query timed out or no data",
        }

    def _publish_state(self, reason: str = "") -> None:
        """Publish gateway.state event via TycheEngine."""
        payload = self.state_machine.to_payload(reason=reason)
        self.send_event("gateway.state", payload)

    def _publish_error(
        self,
        error_id: int,
        error_msg: str,
        source: str = "",
        context: str = "",
    ) -> None:
        """Publish gateway.error event via TycheEngine."""
        self.send_event("gateway.error", {
            "venue": self.venue_name,
            "source": source,
            "error_id": error_id,
            "error_msg": error_msg,
            "context": context,
        })

    def publish_position_update(self, position: Any) -> None:
        """Publish a position update event to the engine."""
        self.send_event("position.update", position.to_dict())
