"""Unit tests for SimulatedGateway."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from modules.trading.gateway.simulated import SimulatedGateway
from modules.trading.models.enums import OrderStatus, OrderType, Side
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.models.tick import Quote, Trade
from tyche.types import Endpoint


class TestSimulatedGateway:
    """Tests for SimulatedGateway connection, orders, and market data."""

    @pytest.fixture
    def gateway(self):
        """Create a SimulatedGateway with mocked ZMQ/publish methods."""
        gw = SimulatedGateway(
            engine_endpoint=Endpoint(host="127.0.0.1", port=5555),
            instruments=["BTCUSDT.simulated.crypto"],
            tick_interval=0.01,
            base_prices={"BTCUSDT.simulated.crypto": Decimal("65000.00")},
            fill_latency=0.0,
            fill_probability=1.0,
        )
        # Mock publish methods to avoid ZMQ
        gw.publish_quote = MagicMock()
        gw.publish_trade = MagicMock()
        gw.publish_fill = MagicMock()
        return gw

    # --- Connection tests ---

    def test_connect_sets_connected_flag(self, gateway):
        """connect sets _connected to True."""
        assert not gateway._connected
        gateway.connect()
        assert gateway._connected

    def test_disconnect_clears_connected_flag(self, gateway):
        """disconnect sets _connected to False."""
        gateway.connect()
        assert gateway._connected
        gateway.disconnect()
        assert not gateway._connected

    # --- Subscription tests ---

    def test_subscribe_market_data_adds_instruments(self, gateway):
        """subscribe_market_data adds new instruments to the list."""
        gateway.subscribe_market_data(["ETHUSDT.simulated.crypto"])
        assert "ETHUSDT.simulated.crypto" in gateway._instruments
        assert "ETHUSDT.simulated.crypto" in gateway._current_prices

    def test_subscribe_market_data_sets_default_price(self, gateway):
        """subscribe_market_data assigns default price for unknown instruments."""
        gateway.subscribe_market_data(["NEWCOIN.simulated.crypto"])
        assert gateway._current_prices["NEWCOIN.simulated.crypto"] == Decimal("100.00")

    # --- Order submission: filled ---

    @patch("modules.trading.gateway.simulated.random.random", return_value=0.5)
    @patch("modules.trading.gateway.simulated.time.sleep")
    def test_submit_order_returns_filled_when_random_below_probability(self, mock_sleep, mock_random, gateway):
        """submit_order returns FILLED when random() < fill_probability."""
        gateway.fill_probability = 0.95
        order = Order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
        )

        result = gateway.submit_order(order)

        assert isinstance(result, OrderUpdate)
        assert result.status == OrderStatus.FILLED
        assert result.order_id == order.order_id
        assert result.instrument_id == order.instrument_id
        assert result.filled_quantity == order.quantity
        assert result.avg_fill_price is not None

    def test_submit_order_returns_rejected_when_random_above_probability(self, gateway):
        """submit_order returns REJECTED when random() >= fill_probability."""
        gateway._fill_probability = 0.5
        order = Order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
        )

        with patch("random.random", return_value=0.99):
            with patch("modules.trading.gateway.simulated.time.sleep"):
                result = gateway.submit_order(order)

        assert isinstance(result, OrderUpdate)
        assert result.status == OrderStatus.REJECTED
        assert result.reason is not None

    @patch("modules.trading.gateway.simulated.random.random", return_value=0.5)
    @patch("modules.trading.gateway.simulated.random.uniform", return_value=0.0005)
    @patch("modules.trading.gateway.simulated.time.sleep")
    def test_submit_order_publishes_fill(self, mock_sleep, mock_uniform, mock_random, gateway):
        """submit_order publishes a Fill event via publish_fill."""
        gateway.fill_probability = 1.0
        order = Order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.5"),
        )

        gateway.submit_order(order)

        gateway.publish_fill.assert_called_once()
        fill = gateway.publish_fill.call_args[0][0]
        assert isinstance(fill, Fill)
        assert fill.order_id == order.order_id
        assert fill.instrument_id == order.instrument_id
        assert fill.side == order.side
        assert fill.quantity == order.quantity
        assert fill.fee >= Decimal("0")

    # --- Order cancellation ---

    def test_cancel_order_returns_cancelled(self, gateway):
        """cancel_order returns CANCELLED status."""
        result = gateway.cancel_order("ord-123", "BTCUSDT.simulated.crypto")

        assert isinstance(result, OrderUpdate)
        assert result.status == OrderStatus.CANCELLED
        assert result.order_id == "ord-123"
        assert result.instrument_id == "BTCUSDT.simulated.crypto"

    # --- Account query ---

    def test_query_account_returns_balances_dict(self, gateway):
        """query_account returns simulated balances."""
        result = gateway.query_account()

        assert result["venue"] == "simulated"
        assert "balances" in result
        balances = result["balances"]
        assert len(balances) == 3
        currencies = {b["currency"] for b in balances}
        assert currencies == {"USDT", "BTC", "ETH"}

    # --- Market data generation ---

    def test_generate_market_data_produces_quote_with_bid_less_than_ask(self, gateway):
        """_generate_market_data produces quotes where bid < ask."""
        gateway._running = True

        def _stop_after_one(*args, **kwargs):
            gateway._running = False
            return False

        gateway._stop_event = MagicMock()
        gateway._stop_event.wait.side_effect = _stop_after_one

        with patch("modules.trading.gateway.simulated.random.gauss", return_value=0.0005):
            with patch("modules.trading.gateway.simulated.random.uniform", side_effect=[0.0002, 0.0004, 1.5, 2.0]):
                with patch("modules.trading.gateway.simulated.random.random", return_value=0.99):
                    with patch("modules.trading.gateway.simulated.time.sleep"):
                        gateway._generate_market_data()

        gateway.publish_quote.assert_called_once()
        quote = gateway.publish_quote.call_args[0][0]
        assert isinstance(quote, Quote)
        assert quote.bid < quote.ask
        assert quote.instrument_id == "BTCUSDT.simulated.crypto"
        assert quote.bid_size > Decimal("0")
        assert quote.ask_size > Decimal("0")

    def test_generate_market_data_produces_trade_occasionally(self, gateway):
        """_generate_market_data produces a trade when random() < 0.3."""
        gateway._running = True

        def _stop_after_one(*args, **kwargs):
            gateway._running = False
            return False

        gateway._stop_event = MagicMock()
        gateway._stop_event.wait.side_effect = _stop_after_one

        with patch("modules.trading.gateway.simulated.random.gauss", return_value=0.0005):
            with patch("modules.trading.gateway.simulated.random.uniform", side_effect=[0.0002, 0.0004, 1.5, 2.0, 0.5]):
                with patch("modules.trading.gateway.simulated.random.random", return_value=0.1):
                    with patch("modules.trading.gateway.simulated.random.choice", return_value=Side.BUY):
                        with patch("modules.trading.gateway.simulated.time.sleep"):
                            gateway._generate_market_data()

        gateway.publish_trade.assert_called_once()
        trade = gateway.publish_trade.call_args[0][0]
        assert isinstance(trade, Trade)
        assert trade.instrument_id == "BTCUSDT.simulated.crypto"
        assert trade.size > Decimal("0")
        assert trade.trade_id is not None

    def test_generate_market_data_no_trade_when_random_high(self, gateway):
        """_generate_market_data does not produce a trade when random() >= 0.3."""
        gateway._running = True

        def _stop_after_one(*args, **kwargs):
            gateway._running = False
            return False

        gateway._stop_event = MagicMock()
        gateway._stop_event.wait.side_effect = _stop_after_one

        with patch("modules.trading.gateway.simulated.random.gauss", return_value=0.0005):
            with patch("modules.trading.gateway.simulated.random.uniform", side_effect=[0.0002, 0.0004, 1.5, 2.0]):
                with patch("modules.trading.gateway.simulated.random.random", return_value=0.99):
                    with patch("modules.trading.gateway.simulated.time.sleep"):
                        gateway._generate_market_data()

        gateway.publish_trade.assert_not_called()

    # --- Edge cases ---

    def test_submit_order_uses_order_price_when_instrument_not_in_prices(self, gateway):
        """submit_order falls back to order.price when instrument has no current price."""
        gateway._current_prices = {}
        order = Order(
            instrument_id="UNKNOWN",
            side=Side.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1.0"),
            price=Decimal("500.00"),
        )

        with patch("modules.trading.gateway.simulated.random.random", return_value=0.0):
            with patch("modules.trading.gateway.simulated.time.sleep"):
                result = gateway.submit_order(order)

        assert result.status == OrderStatus.FILLED
        gateway.publish_fill.assert_called_once()
        fill = gateway.publish_fill.call_args[0][0]
        # Fill price should be near the fallback price
        assert fill.price > Decimal("0")

    def test_default_instruments_and_prices(self):
        """SimulatedGateway initializes with default instruments and prices."""
        gw = SimulatedGateway(
            engine_endpoint=Endpoint(host="127.0.0.1", port=5555),
        )
        assert "BTCUSDT.simulated.crypto" in gw._instruments
        assert "ETHUSDT.simulated.crypto" in gw._instruments
        assert gw._base_prices["BTCUSDT.simulated.crypto"] == Decimal("65000.00")
        assert gw._base_prices["ETHUSDT.simulated.crypto"] == Decimal("3200.00")
