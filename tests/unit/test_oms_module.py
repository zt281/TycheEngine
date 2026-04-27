"""Unit tests for OMSModule."""

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from modules.trading import events
from modules.trading.models.enums import OrderStatus, OrderType, Side
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.oms.module import OMSModule
from tyche.types import Endpoint


def _make_order_payload(
    instrument_id: str = "BTC.binance.crypto",
    side: Side = Side.BUY,
    status: OrderStatus = OrderStatus.NEW,
    quantity: Decimal = Decimal("10"),
    price: Decimal = Decimal("50000"),
    strategy_id: str = "strat_01",
    order_id: str = "order_123",
) -> dict:
    order = Order(
        instrument_id=instrument_id,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=price,
        status=status,
        strategy_id=strategy_id,
        order_id=order_id,
        created_at=time.time(),
        updated_at=time.time(),
    )
    return order.to_dict()


def _make_fill_payload(
    order_id: str,
    quantity: Decimal = Decimal("5"),
    price: Decimal = Decimal("51000"),
    instrument_id: str = "BTC.binance.crypto",
    side: Side = Side.BUY,
) -> dict:
    fill = Fill(
        order_id=order_id,
        instrument_id=instrument_id,
        side=side,
        price=price,
        quantity=quantity,
        timestamp=time.time(),
    )
    return fill.to_dict()


@pytest.fixture
def oms_module():
    with patch("tyche.module.zmq.Context"):
        module = OMSModule(
            engine_endpoint=Endpoint("127.0.0.1", 5555),
            module_id="oms_test",
        )
        module.send_event = MagicMock()
        yield module


class TestHandleOrderApproved:
    def test_stores_order_and_routes_to_gateway(self, oms_module):
        payload = _make_order_payload()
        oms_module._handle_order_approved(payload)

        stored = oms_module.order_store.get_order("order_123")
        assert stored is not None
        assert stored.status == OrderStatus.PENDING_SUBMIT

        oms_module.send_event.assert_any_call(
            "ack_order_execute_binance", stored.to_dict()
        )

    def test_publishes_order_update(self, oms_module):
        payload = _make_order_payload()
        oms_module._handle_order_approved(payload)

        calls = [call for call in oms_module.send_event.call_args_list if call[0][0] == events.ORDER_UPDATE]
        assert len(calls) == 1
        update = OrderUpdate.from_dict(calls[0][0][1])
        assert update.order_id == "order_123"
        assert update.status == OrderStatus.PENDING_SUBMIT


class TestHandleFill:
    def test_apply_fill_and_publish_update_partial(self, oms_module):
        order = Order(
            instrument_id="BTC.binance.crypto",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
            order_id="order_123",
            created_at=time.time(),
            updated_at=time.time(),
        )
        oms_module.order_store.add_order(order)

        fill_payload = _make_fill_payload("order_123", quantity=Decimal("3"), price=Decimal("51000"))
        oms_module._handle_fill(fill_payload)

        updated = oms_module.order_store.get_order("order_123")
        assert updated.filled_quantity == Decimal("3")
        assert updated.status == OrderStatus.PARTIALLY_FILLED

        calls = [call for call in oms_module.send_event.call_args_list if call[0][0] == events.ORDER_UPDATE]
        assert len(calls) == 1
        update = OrderUpdate.from_dict(calls[0][0][1])
        assert update.status == OrderStatus.PARTIALLY_FILLED
        assert update.filled_quantity == Decimal("3")

    def test_apply_fill_and_publish_update_filled(self, oms_module):
        order = Order(
            instrument_id="BTC.binance.crypto",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
            order_id="order_123",
            created_at=time.time(),
            updated_at=time.time(),
        )
        oms_module.order_store.add_order(order)

        fill_payload = _make_fill_payload("order_123", quantity=Decimal("10"), price=Decimal("51000"))
        oms_module._handle_fill(fill_payload)

        updated = oms_module.order_store.get_order("order_123")
        assert updated.status == OrderStatus.FILLED

        calls = [call for call in oms_module.send_event.call_args_list if call[0][0] == events.ORDER_UPDATE]
        assert len(calls) == 1
        update = OrderUpdate.from_dict(calls[0][0][1])
        assert update.status == OrderStatus.FILLED

    def test_unknown_fill_logs_warning(self, oms_module, caplog):
        fill_payload = _make_fill_payload("unknown_order", quantity=Decimal("1"), price=Decimal("100"))
        with caplog.at_level("WARNING", logger="modules.trading.oms.module"):
            oms_module._handle_fill(fill_payload)

        assert "unknown order" in caplog.text.lower()
        oms_module.send_event.assert_not_called()


class TestHandleCancelRequest:
    def test_active_order_routes_cancel(self, oms_module):
        order = Order(
            instrument_id="BTC.binance.crypto",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            price=Decimal("50000"),
            status=OrderStatus.SUBMITTED,
            order_id="order_123",
            created_at=time.time(),
            updated_at=time.time(),
        )
        oms_module.order_store.add_order(order)

        payload = {"order_id": "order_123", "instrument_id": "BTC.binance.crypto"}
        oms_module._handle_cancel_request(payload)

        updated = oms_module.order_store.get_order("order_123")
        assert updated.status == OrderStatus.PENDING_CANCEL

        oms_module.send_event.assert_any_call("ack_order_cancel_binance", payload)

        calls = [call for call in oms_module.send_event.call_args_list if call[0][0] == events.ORDER_UPDATE]
        assert len(calls) == 1
        update = OrderUpdate.from_dict(calls[0][0][1])
        assert update.status == OrderStatus.PENDING_CANCEL

    def test_unknown_order_logs_warning(self, oms_module, caplog):
        payload = {"order_id": "missing_order", "instrument_id": "BTC.binance.crypto"}
        with caplog.at_level("WARNING", logger="modules.trading.oms.module"):
            oms_module._handle_cancel_request(payload)

        assert "unknown order" in caplog.text.lower()
        oms_module.send_event.assert_not_called()

    def test_inactive_order_logs_warning(self, oms_module, caplog):
        order = Order(
            instrument_id="BTC.binance.crypto",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            price=Decimal("50000"),
            status=OrderStatus.FILLED,
            order_id="order_123",
            created_at=time.time(),
            updated_at=time.time(),
        )
        oms_module.order_store.add_order(order)

        payload = {"order_id": "order_123", "instrument_id": "BTC.binance.crypto"}
        with caplog.at_level("WARNING", logger="modules.trading.oms.module"):
            oms_module._handle_cancel_request(payload)

        assert "inactive order" in caplog.text.lower()
        oms_module.send_event.assert_not_called()


class TestExtractVenue:
    def test_extract_venue_standard_format(self, oms_module):
        assert oms_module._extract_venue("BTC.binance.crypto") == "binance"

    def test_extract_venue_futures_format(self, oms_module):
        assert oms_module._extract_venue("ES.cme.futures") == "cme"

    def test_extract_venue_no_dots_returns_unknown(self, oms_module):
        assert oms_module._extract_venue("BTC") == "unknown"

    def test_extract_venue_single_dot_returns_second_part(self, oms_module):
        assert oms_module._extract_venue("BTC.binance") == "binance"
