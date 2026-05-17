"""OpenCTP Gateway - TycheModule that bridges CTP market data into Tyche Engine."""

import logging
import queue
import tempfile
import threading
from typing import List

from openctp_tts import mdapi

from tyche.module import TycheModule
from tyche.types import Endpoint

from .config import GatewayConfig
from .md_spi import MdSpi

logger = logging.getLogger(__name__)


class OpenCtpGateway(TycheModule):
    """Gateway module that connects to OpenCTP and publishes quote events.

    Lifecycle:
        1. ``__init__`` discovers the ``send_quote`` interface automatically.
        2. ``start()`` registers with TycheEngine, then resolves instruments
           by querying the static_data module for each configured underlying.
        3. Once instruments are resolved, CTP MD API is started and
           subscribes to all resolved InstrumentIDs.
        4. CTP callbacks (in a CTP internal thread) invoke ``_on_tick``,
           which publishes the tick as a ``quote`` event through the engine.
        5. ``stop()`` releases CTP resources, then tears down the module.
    """

    def __init__(self, config: GatewayConfig):
        super().__init__(
            engine_endpoint=Endpoint(config.engine_host, config.engine_port),
            family_name="openctp_gateway",
        )
        self.config = config
        self._md_api: mdapi.CThostFtdcMdApi | None = None
        self._md_spi: MdSpi | None = None
        self._resolved_instruments: List[str] = []

        # Tick routing statistics for debugging
        self._quote_count = 0
        self._job_count = 0
        self._tick_drop_count = 0

        # Tick queue for non-blocking CTP callback processing.
        # CTP callbacks put ticks into the queue (fast, never blocks),
        # and a background worker thread processes them sequentially.
        # This prevents request_compute_greeks from freezing the CTP thread.
        self._tick_queue: queue.Queue = queue.Queue(maxsize=50000)
        self._tick_worker_thread: threading.Thread | None = None

    # ── Producer declarations (auto-discovered) ──────────────────

    def send_quote(self, payload: dict) -> None:
        """Declare quote event producer - auto-discovered by TycheModule."""
        self.send_event("quote", payload)

    def request_compute_greeks(self, payload: dict) -> dict:
        """Declare compute_greeks job requester - auto-discovered by TycheModule.

        Used for option ticks that should be processed by exactly one
        GreeksEngine via round-robin job routing.
        """
        return self.request_event("compute_greeks", payload, timeout=5.0)

    # ── Instrument resolution via static_data ─────────────────────

    def _resolve_instruments(self) -> List[str]:
        """Query static_data module to resolve underlyings into instrument IDs.

        For each exchange_id -> [product_ids] pair in ``underlyings``, sends a
        ``query_instruments`` job request per product to the static_data module.
        Collects all returned InstrumentIDs for CTP subscription.

        Queries both futures (product_id) and options. Option product IDs vary
        by exchange:
            - SHFE/DCE/INE/GFEX: {product_id}_o
            - CZCE: {product_id}C or {product_id}P
            - CFFEX: same as futures (IO, HO, MO)

        Returns:
            List of instrument ID strings for CTP subscription.
        """
        if not self.config.underlyings:
            logger.warning(
                "[OpenCtpGateway] No underlyings configured, "
                "nothing to subscribe"
            )
            return []

        all_instruments: List[str] = []

        for exchange_id, product_ids in self.config.underlyings.items():
            for product_id in product_ids:
                # Query futures for the underlying
                payload = {"exchange_id": exchange_id}
                if product_id:
                    payload["product_id"] = product_id

                instruments = self._query_instruments(
                    exchange_id, product_id, payload
                )
                all_instruments.extend(instruments)

                # Query options based on exchange-specific naming
                option_product_ids: List[str] = []
                if exchange_id in ("SHFE", "DCE", "INE", "GFEX"):
                    option_product_ids = [f"{product_id}_o"]
                elif exchange_id == "CZCE":
                    option_product_ids = [f"{product_id}C", f"{product_id}P"]
                elif exchange_id == "CFFEX":
                    # CFFEX options share the same product_id as futures
                    option_product_ids = [product_id]

                for opt_pid in option_product_ids:
                    if not opt_pid:
                        continue
                    option_payload = {
                        "exchange_id": exchange_id,
                        "product_id": opt_pid,
                    }
                    option_instruments = self._query_instruments(
                        exchange_id, opt_pid, option_payload
                    )
                    all_instruments.extend(option_instruments)

        return all_instruments

    def _query_instruments(
        self, exchange_id: str, product_id: str, payload: dict
    ) -> List[str]:
        """Send a single query_instruments job and return instrument IDs."""
        logger.info(
            "[OpenCtpGateway] Querying static_data for underlying: "
            "product_id=%s, exchange_id=%s",
            product_id,
            exchange_id,
        )

        try:
            result = self.request_event(
                "query_instruments",
                payload,
                timeout=self.config.resolve_timeout,
            )
        except TimeoutError:
            logger.error(
                "[OpenCtpGateway] Timeout querying static_data for "
                "product_id=%s, exchange_id=%s — skipping",
                product_id,
                exchange_id,
            )
            return []
        except Exception as e:
            logger.error(
                "[OpenCtpGateway] Error querying static_data for "
                "product_id=%s, exchange_id=%s: %s — skipping",
                product_id,
                exchange_id,
                e,
            )
            return []

        # request_event wraps handler return value in {"result": ...}
        # So we need to unwrap: {"result": {"instruments": [...]}}
        if "error" in result:
            logger.error(
                "[OpenCtpGateway] query_instruments returned error "
                "for product_id=%s, exchange_id=%s: %s",
                product_id,
                exchange_id,
                result["error"],
            )
            return []

        inner = result.get("result", {})
        instruments = inner.get("instruments", [])
        instrument_ids: List[str] = []
        for inst in instruments:
            instrument_id = inst.get("InstrumentID", "")
            # 期权判断：ticker名长度大于7个字符的是期权，否则为期货
            is_option = len(instrument_id) > 7
            if not instrument_id:
                continue
            # 期货直接订阅；期权也直接订阅（不再受 subscribe_options 开关限制）
            instrument_ids.append(instrument_id)

        logger.info(
            "[OpenCtpGateway] Resolved %d instruments for "
            "product_id=%s, exchange_id=%s",
            len(instrument_ids),
            product_id,
            exchange_id,
        )
        return instrument_ids

    # ── Tick callback from CTP SPI ───────────────────────────────

    def _on_tick(self, tick_data: dict) -> None:
        """Callback invoked from MdSpi when a new tick arrives.

        This is called from the CTP internal thread. We enqueue the tick
        for async processing to avoid blocking the CTP thread —
        ``request_compute_greeks`` can block for seconds when the
        GreeksEngine is unavailable, which would freeze all CTP callbacks.
        """
        try:
            self._tick_queue.put_nowait(tick_data)
        except queue.Full:
            self._tick_drop_count += 1
            logger.warning(
                "[OpenCtpGateway] Tick queue full, dropping: %s",
                tick_data.get("instrument_id", ""),
            )

    def _tick_worker(self) -> None:
        """Background worker that drains the tick queue and processes ticks.

        Runs in a dedicated thread so that blocking ``request_compute_greeks``
        calls never freeze the CTP callback thread.
        """
        while self._running:
            try:
                tick_data = self._tick_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._process_tick(tick_data)

    def _process_tick(self, tick_data: dict) -> None:
        """Process a single tick (routing logic, runs in tick worker thread).

        Routing strategy:
        - Future (underlying) ticks -> broadcast via ``quote`` topic
          (all GreeksEngines receive and update local cache)
        - Option ticks -> broadcast + job request ``compute_greeks``
          (exactly one GreeksEngine handles via round-robin)
        """
        instrument_id = tick_data.get("instrument_id", "")
        last_price = tick_data.get("last_price", 0.0)

        if not instrument_id:
            self._tick_drop_count += 1
            logger.warning(
                "[OpenCtpGateway] Dropping tick #%d with empty instrument_id",
                self._tick_drop_count,
            )
            return

        # Log first few ticks for visibility
        total_routed = self._quote_count + self._job_count
        if total_routed < 5:
            logger.info(
                "[OpenCtpGateway] Tick received: %s price=%.2f",
                instrument_id,
                last_price,
            )

        # 判断期货还是期权：ticker名长度大于7个字符的是期权，否则为期货
        is_option = len(instrument_id) > 7
        if is_option:
            # Option tick -> broadcast + job mode
            self._job_count += 1
            self.send_quote(tick_data)
            try:
                result = self.request_compute_greeks(tick_data)
                if self._job_count <= 5 or self._job_count % 100 == 0:
                    logger.info(
                        "[OpenCtpGateway] Option quote job #%d: %s price=%.2f",
                        self._job_count,
                        instrument_id,
                        last_price,
                    )
                else:
                    logger.debug(
                        "[OpenCtpGateway] Option quote job #%d: %s price=%.2f",
                        self._job_count,
                        instrument_id,
                        last_price,
                    )
            except Exception as e:
                logger.warning(
                    "[OpenCtpGateway] compute_greeks job #%d failed for %s: %s",
                    self._job_count,
                    instrument_id,
                    e,
                )
        else:
            # Future/underlying tick -> broadcast mode (all consumers)
            self._quote_count += 1
            self.send_quote(tick_data)
            if self._quote_count <= 5 or self._quote_count % 100 == 0:
                logger.info(
                    "[OpenCtpGateway] Quote broadcast #%d: %s price=%.2f",
                    self._quote_count,
                    instrument_id,
                    last_price,
                )
            else:
                logger.debug(
                    "[OpenCtpGateway] Quote broadcast #%d: %s price=%.2f",
                    self._quote_count,
                    instrument_id,
                    last_price,
                )

    # ── Start / Stop ─────────────────────────────────────────────

    def start(self) -> None:
        """Start the module: register with engine, resolve instruments, then connect CTP MD."""
        super().start()
        self._resolved_instruments = self._resolve_instruments()

        # Start background tick worker before CTP MD connection
        self._tick_worker_thread = threading.Thread(
            target=self._tick_worker, name="tick_worker", daemon=True,
        )
        self._tick_worker_thread.start()

        # 分离期货和期权，用于日志展示
        futures = [i for i in self._resolved_instruments if len(i) <= 7]
        options = [i for i in self._resolved_instruments if len(i) > 7]

        logger.info(
            "[OpenCtpGateway] Resolved %d instruments for subscription "
            "(%d futures, %d options)",
            len(self._resolved_instruments),
            len(futures),
            len(options),
        )
        if futures:
            logger.info("[OpenCtpGateway] Futures: %s", futures)
        if options:
            logger.info("[OpenCtpGateway] Options: %s", options)
        self._start_md()

    def _start_md(self) -> None:
        """Initialize and connect CTP Market Data API."""
        # Use a temporary directory for CTP flow files
        flow_path = tempfile.mkdtemp(prefix="openctp_md_") + "/"

        logger.info(
            "[OpenCtpGateway] Creating MD API, flow_path=%s, front=%s",
            flow_path,
            self.config.md_front,
        )

        self._md_api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(flow_path)

        self._md_spi = MdSpi(
            md_api=self._md_api,
            broker_id=self.config.broker_id,
            user_id=self.config.user_id,
            password=self.config.password,
            instruments=self._resolved_instruments,
            on_tick=self._on_tick,
            subscribe_for_quote=False,
        )

        self._md_api.RegisterSpi(self._md_spi)
        self._md_api.RegisterFront(self.config.md_front)
        self._md_api.Init()

        logger.info("[OpenCtpGateway] MD API initialized, waiting for connection...")

    def stop(self) -> None:
        """Stop CTP connections and the module."""
        logger.info(
            "[OpenCtpGateway] Stopping... (quotes=%d, jobs=%d, dropped=%d, queue=%d)",
            self._quote_count,
            self._job_count,
            self._tick_drop_count,
            self._tick_queue.qsize(),
        )

        if self._md_api is not None:
            self._md_api.RegisterSpi(None)
            self._md_api.Release()
            self._md_api = None
            self._md_spi = None

        super().stop()
        logger.info("[OpenCtpGateway] Stopped")
