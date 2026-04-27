"""Unit tests for PortfolioModule."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from modules.trading.models.enums import PositionSide, Side
from modules.trading.models.order import Fill
from modules.trading.models.position import Position
from modules.trading.portfolio.module import PortfolioModule
from tyche.types import Endpoint


@pytest.fixture
def mock_endpoint():
    return Endpoint(host="127.0.0.1", port=5555)


@pytest.fixture
def portfolio(mock_endpoint):
    """Return a PortfolioModule with send_event mocked."""
    module = PortfolioModule(engine_endpoint=mock_endpoint, module_id="test-portfolio")
    module._pub_socket = MagicMock()
    return module


def _fill(order_id, instrument_id, side, price, quantity):
    return Fill(
        order_id=order_id,
        instrument_id=instrument_id,
        side=side,
        price=Decimal(str(price)),
        quantity=Decimal(str(quantity)),
        timestamp=0.0,
    )


class TestHandleFill:
    """Tests for _handle_fill behavior."""

    def test_buy_fill_increases_long_position(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        pos = portfolio.get_position("BTC-USD")
        assert pos.side == PositionSide.LONG
        assert pos.quantity == Decimal("10")
        assert pos.avg_entry_price == Decimal("100")

    def test_second_buy_fill_updates_avg_entry_price(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_fill(_fill("o2", "BTC-USD", Side.BUY, 200, 10).to_dict())
        pos = portfolio.get_position("BTC-USD")
        assert pos.quantity == Decimal("20")
        assert pos.avg_entry_price == Decimal("150")

    def test_sell_fill_decreases_long_position(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_fill(_fill("o2", "BTC-USD", Side.SELL, 120, 6).to_dict())
        pos = portfolio.get_position("BTC-USD")
        assert pos.side == PositionSide.LONG
        assert pos.quantity == Decimal("4")
        assert pos.realized_pnl == Decimal("120")

    def test_sell_fill_creates_short_when_exceeds_long(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_fill(_fill("o2", "BTC-USD", Side.SELL, 120, 15).to_dict())
        pos = portfolio.get_position("BTC-USD")
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == Decimal("5")
        assert pos.avg_entry_price == Decimal("120")

    def test_handle_fill_publishes_position_update(self, portfolio):
        with patch.object(portfolio, "send_event") as mock_send:
            portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
            mock_send.assert_called_once()
            event_name, payload = mock_send.call_args.args
            assert event_name == "position.update"
            assert payload["instrument_id"] == "BTC-USD"


class TestHandleQuote:
    """Tests for _handle_quote behavior."""

    def test_quote_updates_mark_price_and_unrealized_pnl(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        with patch.object(portfolio, "send_event"):
            portfolio._handle_quote({"instrument_id": "BTC-USD", "bid": "110", "ask": "112"})
        pos = portfolio.get_position("BTC-USD")
        assert pos.last_price == Decimal("111")
        assert pos.unrealized_pnl == Decimal("110")

    def test_quote_publishes_only_if_pnl_change_exceeds_threshold(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        with patch.object(portfolio, "send_event") as mock_send:
            portfolio._handle_quote({"instrument_id": "BTC-USD", "bid": "100.001", "ask": "100.001"})
            mock_send.assert_not_called()

    def test_quote_publishes_when_pnl_change_is_material(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        with patch.object(portfolio, "send_event") as mock_send:
            portfolio._handle_quote({"instrument_id": "BTC-USD", "bid": "110", "ask": "110"})
            mock_send.assert_called_once()

    def test_quote_ignores_unknown_instrument(self, portfolio):
        with patch.object(portfolio, "send_event") as mock_send:
            portfolio._handle_quote({"instrument_id": "ETH-USD", "bid": "200", "ask": "202"})
            mock_send.assert_not_called()


class TestGetPosition:
    """Tests for get_position behavior."""

    def test_returns_flat_position_for_unknown_instrument(self, portfolio):
        pos = portfolio.get_position("UNKNOWN")
        assert pos.instrument_id == "UNKNOWN"
        assert pos.side == PositionSide.FLAT
        assert pos.quantity == Decimal("0")

    def test_returns_existing_position(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        assert portfolio.get_position("BTC-USD").quantity == Decimal("10")


class TestGetAllPositions:
    """Tests for get_all_positions behavior."""

    def test_returns_copy_of_positions_dict(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        all_positions = portfolio.get_all_positions()
        assert "BTC-USD" in all_positions
        assert all_positions["BTC-USD"].quantity == Decimal("10")
        all_positions["NEW"] = Position(instrument_id="NEW")
        assert "NEW" not in portfolio.get_all_positions()


class TestPnlProperties:
    """Tests for total realized and unrealized PnL properties."""

    def test_total_realized_pnl(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_fill(_fill("o2", "BTC-USD", Side.SELL, 120, 10).to_dict())
        assert portfolio.total_realized_pnl == Decimal("200")

    def test_total_unrealized_pnl(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_quote({"instrument_id": "BTC-USD", "bid": "110", "ask": "110"})
        assert portfolio.total_unrealized_pnl == Decimal("100")

    def test_pnl_across_multiple_instruments(self, portfolio):
        portfolio._handle_fill(_fill("o1", "BTC-USD", Side.BUY, 100, 10).to_dict())
        portfolio._handle_fill(_fill("o2", "ETH-USD", Side.BUY, 50, 5).to_dict())
        portfolio._handle_quote({"instrument_id": "BTC-USD", "bid": "110", "ask": "110"})
        portfolio._handle_quote({"instrument_id": "ETH-USD", "bid": "55", "ask": "55"})
        assert portfolio.total_unrealized_pnl == Decimal("125")
