"""OpenCTP Gateway module - connects to CTP/TTS and publishes market data.

This module:
1. Connects to the TTS Trade API to query available instruments
2. Filters instruments based on configured underlyings (exchange -> products)
3. Connects to the TTS Market Data API and subscribes to filtered instruments
4. Publishes received market data as 'quote' events to TycheEngine
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.modules.openctp_gateway.config import GatewayConfig
from src.modules.openctp_gateway.md_spi import MdSpi
from src.modules.openctp_gateway.td_spi import TdSpi
from src.tyche.module import TycheModule
from src.tyche.types import Endpoint

logger = logging.getLogger(__name__)


class OpenCtpGateway(TycheModule):
    """OpenCTP/TTS Gateway module for TycheEngine.

    Connects to CTP-compatible trading front, queries instruments,
    subscribes to market data, and publishes quotes to the engine.
    """

    def __init__(
        self,
        config: GatewayConfig,
        md_module: Any,
        td_module: Any,
    ):
        """Initialize the gateway.

        Args:
            config: Gateway configuration
            md_module: Imported CTP market data API module
            td_module: Imported CTP trader API module
        """
        engine_endpoint = Endpoint(config.engine_host, config.engine_port)
        heartbeat_endpoint = Endpoint(config.engine_host, config.engine_port + 5)
        super().__init__(
            engine_endpoint=engine_endpoint,
            family_name="openctp_gateway",
            heartbeat_receive_endpoint=heartbeat_endpoint,
        )

        self.config = config
        self._md_module = md_module
        self._td_module = td_module

        # SPI instances
        self._md_spi = None  # type: Optional[MdSpi]
        self._td_spi = None  # type: Optional[TdSpi]

        # Subscribed instruments
        self._subscribed_instruments = []  # type: List[str]

    def start(self) -> None:
        """Start the gateway module.

        Lifecycle:
        1. Register with TycheEngine (via super().start())
        2. Connect trade API and query instruments
        3. Filter instruments by configured underlyings
        4. Connect market data API and subscribe
        """
        super().start()

        # Connect trade API first for instrument query
        self._connect_td()

        # Then connect market data API
        self._connect_md()

    def stop(self) -> None:
        """Stop the gateway and release all API resources."""
        logger.info("Stopping OpenCTP Gateway...")

        # Release MD API
        if self._md_spi is not None:
            try:
                self._md_spi.release()
            except Exception as e:
                logger.debug("MdSpi release error: %s", e)
            self._md_spi = None

        # Release TD API
        if self._td_spi is not None:
            try:
                self._td_spi.release()
            except Exception as e:
                logger.debug("TdSpi release error: %s", e)
            self._td_spi = None

        super().stop()
        logger.info("OpenCTP Gateway stopped")

    def send_quote(self, payload: dict) -> None:
        """Declare this module as a quote event producer.

        This method's existence (send_ prefix) registers the 'quote'
        interface as a producer during handler discovery.
        The actual publishing is done via self.send_event().
        """
        pass

    def _on_market_data(self, data: dict) -> None:
        """Callback from MdSpi - publish quote event to engine.

        Args:
            data: Parsed market data dictionary from MdSpi
        """
        self.send_event("quote", data)

    def _connect_td(self) -> None:
        """Connect trade API, login, and query instruments."""
        if not self.config.td_front:
            logger.warning("No td_front configured, skipping trade API connection")
            return

        logger.info(
            "TD connect: front=%s broker_id=%s user_id=%s",
            self.config.td_front, self.config.broker_id, self.config.user_id,
        )

        self._td_spi = TdSpi(
            td_module=self._td_module,
            front_addr=self.config.td_front,
            broker_id=self.config.broker_id,
            user_id=self.config.user_id,
            password=self.config.password,
        )

        self._td_spi.connect()

        if not self._td_spi.wait_login(timeout=10.0):
            logger.error(
                "Trade API login timeout (connected=%s)",
                self._td_spi.connected,
            )
            return

        # Query instruments
        # Small delay to ensure API is ready (CTP requires this)
        time.sleep(1.0)
        self._td_spi.query_instruments()

        if not self._td_spi.wait_instruments(timeout=30.0):
            logger.error("Instrument query timeout")
            return

        logger.info(
            "TD instruments received: total=%d",
            len(self._td_spi.instruments),
        )

        # Filter instruments based on configured underlyings
        self._subscribed_instruments = self._filter_instruments(
            self._td_spi.instruments
        )
        logger.info(
            "Filtered %d instruments for subscription (underlyings=%s)",
            len(self._subscribed_instruments), self.config.underlyings,
        )

    def _connect_md(self) -> None:
        """Connect market data API and subscribe to instruments."""
        if not self.config.md_front:
            logger.warning("No md_front configured, skipping market data connection")
            return

        logger.info(
            "MD connect: front=%s broker_id=%s user_id=%s",
            self.config.md_front, self.config.broker_id, self.config.user_id,
        )

        self._md_spi = MdSpi(
            md_module=self._md_module,
            on_data_callback=self._on_market_data,
            front_addr=self.config.md_front,
            broker_id=self.config.broker_id,
            user_id=self.config.user_id,
            password=self.config.password,
        )

        self._md_spi.connect()

        if not self._md_spi.wait_login(timeout=10.0):
            logger.error(
                "Market data API login timeout (connected=%s)",
                self._md_spi.connected,
            )
            return

        # Subscribe to filtered instruments
        if self._subscribed_instruments:
            self._subscribe_instruments(self._subscribed_instruments)
        else:
            logger.warning(
                "No instruments to subscribe (TD login or instrument query failed)"
            )

    def _subscribe_instruments(self, instruments: List[str]) -> None:
        """Subscribe to market data for a list of instruments.

        Args:
            instruments: List of instrument IDs
        """
        if self._md_spi is None:
            return

        # Subscribe in batches to avoid overwhelming the API
        batch_size = 500
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            self._md_spi.subscribe(batch)
            if i + batch_size < len(instruments):
                time.sleep(0.5)  # Small delay between batches

    def _filter_instruments(self, instruments: List[dict]) -> List[str]:
        """Filter instruments based on configured underlyings.

        The underlyings config maps exchange -> list of product IDs.
        An instrument matches if its exchange_id and product_id match.

        If underlyings is empty, subscribe to ALL instruments.

        Args:
            instruments: List of instrument info dicts from TdSpi

        Returns:
            List of instrument IDs to subscribe
        """
        underlyings = self.config.underlyings
        if not underlyings:
            # No filter configured - subscribe to all
            return [inst["instrument_id"] for inst in instruments]

        result = []
        for inst in instruments:
            exchange = inst.get("exchange_id", "")
            product_id = inst.get("product_id", "").strip()

            # Check if this exchange is in our config
            if exchange not in underlyings:
                continue

            # Check if product matches any configured underlying
            configured_products = underlyings[exchange]
            if not configured_products:
                # Empty product list = all products on this exchange
                result.append(inst["instrument_id"])
            elif product_id in configured_products:
                result.append(inst["instrument_id"])

        return result
