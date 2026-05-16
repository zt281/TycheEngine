"""CTP Market Data SPI - receives callbacks from CTP MD API."""

import logging
import sys
from typing import Callable, Optional

from openctp_tts import mdapi

logger = logging.getLogger(__name__)

# CTP uses DBL_MAX (1.7976931348623157e+308) to indicate invalid/empty prices
_DBL_MAX = sys.float_info.max


def _safe_price(value: float) -> float:
    """Return 0.0 for CTP invalid prices (DBL_MAX), otherwise the value."""
    if value is None or value >= _DBL_MAX:
        return 0.0
    return value


def _safe_str(value) -> str:
    """Decode CTP string fields from bytes to str, or return empty string."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class MdSpi(mdapi.CThostFtdcMdSpi):
    """CTP Market Data SPI implementation.

    Receives market data callbacks from CTP and forwards tick data
    to the gateway via a callback function.

    Args:
        md_api: CTP MD API instance.
        broker_id: Broker ID for login.
        user_id: User ID for login.
        password: Password for login.
        instruments: List of instrument IDs to subscribe after login.
        on_tick: Callback invoked with a tick_data dict on each tick.
    """

    def __init__(
        self,
        md_api: mdapi.CThostFtdcMdApi,
        broker_id: str,
        user_id: str,
        password: str,
        instruments: list[str],
        on_tick: Callable[[dict], None],
        subscribe_for_quote: bool = True,
    ):
        super().__init__()
        self._api = md_api
        self._broker_id = broker_id
        self._user_id = user_id
        self._password = password
        self._instruments = instruments
        self._on_tick = on_tick
        self._subscribe_for_quote = subscribe_for_quote

        # Tick statistics for debugging
        self._tick_count = 0
        self._last_tick_instrument = ""
        self._last_tick_time = ""

    # ── Connection callbacks ─────────────────────────────────────

    def OnFrontConnected(self) -> None:
        """Called when connection to the MD front is established."""
        logger.info("[MdSpi] Front connected, sending login request")
        logger.debug(
            "[MdSpi] Login params: broker_id=%s, user_id=%s, password=%s",
            self._broker_id,
            self._user_id,
            "***" if self._password else "(empty)",
        )

        req = mdapi.CThostFtdcReqUserLoginField()
        req.BrokerID = self._broker_id
        req.UserID = self._user_id
        req.Password = self._password

        ret = self._api.ReqUserLogin(req, 0)
        if ret != 0:
            logger.error("[MdSpi] ReqUserLogin failed, ret=%d", ret)
        else:
            logger.debug("[MdSpi] ReqUserLogin sent successfully")

    def OnFrontDisconnected(self, nReason: int) -> None:
        """Called when disconnected from the MD front."""
        logger.warning("[MdSpi] Front disconnected, reason=%d", nReason)
        logger.info(
            "[MdSpi] Tick stats before disconnect: total_ticks=%d, last_instrument=%s, last_time=%s",
            self._tick_count,
            self._last_tick_instrument,
            self._last_tick_time,
        )

    # ── Login callback ───────────────────────────────────────────

    def OnRspUserLogin(
        self,
        pRspUserLogin: mdapi.CThostFtdcRspUserLoginField,
        pRspInfo: mdapi.CThostFtdcRspInfoField,
        nRequestID: int,
        bIsLast: bool,
    ) -> None:
        """Called on login response."""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = _safe_str(pRspInfo.ErrorMsg)
            logger.error(
                "[MdSpi] Login failed: ErrorID=%d, ErrorMsg=%s",
                pRspInfo.ErrorID,
                error_msg,
            )
            return

        trading_day = _safe_str(pRspUserLogin.TradingDay) if pRspUserLogin else "N/A"
        logger.info(
            "[MdSpi] Login succeeded, TradingDay=%s",
            trading_day,
        )

        if self._instruments:
            logger.info("[MdSpi] Subscribing to %d instruments", len(self._instruments))
            logger.debug("[MdSpi] Instrument list: %s", self._instruments)
            encoded = [inst.encode("utf-8") for inst in self._instruments]
            ret = self._api.SubscribeMarketData(encoded, len(self._instruments))
            if ret != 0:
                logger.error("[MdSpi] SubscribeMarketData failed, ret=%d", ret)
            else:
                logger.debug("[MdSpi] SubscribeMarketData sent successfully")

            # Subscribe to option for-quote responses if enabled
            if self._subscribe_for_quote:
                logger.info(
                    "[MdSpi] Subscribing to ForQuoteRsp for %d instruments",
                    len(self._instruments),
                )
                ret_fq = self._api.SubscribeForQuoteRsp(encoded, len(self._instruments))
                if ret_fq != 0:
                    logger.error(
                        "[MdSpi] SubscribeForQuoteRsp failed, ret=%d", ret_fq
                    )
                else:
                    logger.debug("[MdSpi] SubscribeForQuoteRsp sent successfully")
        else:
            logger.warning("[MdSpi] No instruments configured, nothing to subscribe")

    # ── Market data callback ─────────────────────────────────────

    def OnRtnDepthMarketData(
        self,
        pDepthMarketData: mdapi.CThostFtdcDepthMarketDataField,
    ) -> None:
        """Called on each market data tick."""
        if pDepthMarketData is None:
            logger.warning("[MdSpi] OnRtnDepthMarketData called with None data")
            return

        instrument_id = _safe_str(pDepthMarketData.InstrumentID)
        update_time = _safe_str(pDepthMarketData.UpdateTime)
        last_price = _safe_price(pDepthMarketData.LastPrice)

        self._tick_count += 1
        self._last_tick_instrument = instrument_id
        self._last_tick_time = update_time

        # Log first tick and every 100th tick for visibility
        if self._tick_count == 1:
            logger.info(
                "[MdSpi] First tick received: %s @ %s price=%.2f",
                instrument_id,
                update_time,
                last_price,
            )
        elif self._tick_count % 100 == 0:
            logger.info(
                "[MdSpi] Tick milestone: %d ticks received, last=%s @ %s",
                self._tick_count,
                instrument_id,
                update_time,
            )

        logger.debug(
            "[MdSpi] Tick #%d: %s price=%.2f bid=%.2f ask=%.2f vol=%d",
            self._tick_count,
            instrument_id,
            last_price,
            _safe_price(pDepthMarketData.BidPrice1),
            _safe_price(pDepthMarketData.AskPrice1),
            pDepthMarketData.Volume,
        )

        tick_data = {
            "instrument_id": instrument_id,
            "exchange_id": _safe_str(pDepthMarketData.ExchangeID),
            "last_price": last_price,
            "bid_price_1": _safe_price(pDepthMarketData.BidPrice1),
            "bid_volume_1": pDepthMarketData.BidVolume1,
            "ask_price_1": _safe_price(pDepthMarketData.AskPrice1),
            "ask_volume_1": pDepthMarketData.AskVolume1,
            "volume": pDepthMarketData.Volume,
            "open_interest": _safe_price(pDepthMarketData.OpenInterest),
            "open_price": _safe_price(pDepthMarketData.OpenPrice),
            "high_price": _safe_price(pDepthMarketData.HighestPrice),
            "low_price": _safe_price(pDepthMarketData.LowestPrice),
            "pre_close_price": _safe_price(pDepthMarketData.PreClosePrice),
            "pre_settlement_price": _safe_price(pDepthMarketData.PreSettlementPrice),
            "upper_limit_price": _safe_price(pDepthMarketData.UpperLimitPrice),
            "lower_limit_price": _safe_price(pDepthMarketData.LowerLimitPrice),
            "update_time": update_time,
            "update_millisec": pDepthMarketData.UpdateMillisec,
            "trading_day": _safe_str(pDepthMarketData.TradingDay),
        }

        self._on_tick(tick_data)

    # ── Error callback ───────────────────────────────────────────

    def OnRspError(
        self,
        pRspInfo: mdapi.CThostFtdcRspInfoField,
        nRequestID: int,
        bIsLast: bool,
    ) -> None:
        """Called on error response."""
        if pRspInfo:
            error_msg = _safe_str(pRspInfo.ErrorMsg)
            logger.error(
                "[MdSpi] Error: ErrorID=%d, ErrorMsg=%s",
                pRspInfo.ErrorID,
                error_msg,
            )

    # ── Subscription callbacks ───────────────────────────────────

    def OnRspSubMarketData(
        self,
        pSpecificInstrument: mdapi.CThostFtdcSpecificInstrumentField,
        pRspInfo: mdapi.CThostFtdcRspInfoField,
        nRequestID: int,
        bIsLast: bool,
    ) -> None:
        """Called on subscription response."""
        inst_id = _safe_str(pSpecificInstrument.InstrumentID) if pSpecificInstrument else "?"
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = _safe_str(pRspInfo.ErrorMsg)
            logger.error(
                "[MdSpi] Subscribe failed for %s: ErrorID=%d, ErrorMsg=%s",
                inst_id,
                pRspInfo.ErrorID,
                error_msg,
            )
        elif pSpecificInstrument:
            logger.info(
                "[MdSpi] Subscribed: %s", inst_id
            )
