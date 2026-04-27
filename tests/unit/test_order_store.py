"""Unit tests for OrderStore."""

import threading
import time
from decimal import Decimal

from modules.trading.models.enums import OrderStatus, OrderType, Side
from modules.trading.models.order import Fill, Order
from modules.trading.oms.order_store import OrderStore


def _make_order(
    instrument_id: str = "BTC.binance.crypto",
    side: Side = Side.BUY,
    status: OrderStatus = OrderStatus.NEW,
    quantity: Decimal = Decimal("10"),
    strategy_id: str = "strat_01",
    price: Decimal = Decimal("50000"),
) -> Order:
    return Order(
        instrument_id=instrument_id,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=price,
        status=status,
        strategy_id=strategy_id,
        created_at=time.time(),
        updated_at=time.time(),
    )


def _make_fill(
    order_id: str,
    quantity: Decimal = Decimal("5"),
    price: Decimal = Decimal("51000"),
    instrument_id: str = "BTC.binance.crypto",
    side: Side = Side.BUY,
) -> Fill:
    return Fill(
        order_id=order_id,
        instrument_id=instrument_id,
        side=side,
        price=price,
        quantity=quantity,
        timestamp=time.time(),
    )


class TestAddAndGet:
    def test_add_order_stores_and_get_order_retrieves(self):
        store = OrderStore()
        order = _make_order()
        store.add_order(order)

        retrieved = store.get_order(order.order_id)
        assert retrieved is order

    def test_get_order_returns_none_for_unknown(self):
        store = OrderStore()
        assert store.get_order("unknown_id") is None


class TestUpdateStatus:
    def test_valid_transition_new_to_submitted(self):
        store = OrderStore()
        order = _make_order(status=OrderStatus.NEW)
        store.add_order(order)

        result = store.update_status(order.order_id, OrderStatus.PENDING_SUBMIT)
        assert result is order
        assert order.status == OrderStatus.PENDING_SUBMIT

        result = store.update_status(order.order_id, OrderStatus.SUBMITTED)
        assert result is order
        assert order.status == OrderStatus.SUBMITTED

    def test_valid_transition_submitted_to_filled(self):
        store = OrderStore()
        order = _make_order(status=OrderStatus.SUBMITTED)
        store.add_order(order)

        result = store.update_status(order.order_id, OrderStatus.FILLED)
        assert result is order
        assert order.status == OrderStatus.FILLED

    def test_invalid_transition_filled_to_cancelled_returns_none(self):
        store = OrderStore()
        order = _make_order(status=OrderStatus.FILLED)
        store.add_order(order)

        result = store.update_status(order.order_id, OrderStatus.CANCELLED)
        assert result is None
        assert order.status == OrderStatus.FILLED

    def test_invalid_transition_new_to_filled_returns_none(self):
        store = OrderStore()
        order = _make_order(status=OrderStatus.NEW)
        store.add_order(order)

        result = store.update_status(order.order_id, OrderStatus.FILLED)
        assert result is None
        assert order.status == OrderStatus.NEW

    def test_update_status_sets_venue_order_id(self):
        store = OrderStore()
        order = _make_order(status=OrderStatus.PENDING_SUBMIT)
        store.add_order(order)

        store.update_status(
            order.order_id, OrderStatus.SUBMITTED, venue_order_id="venue_123"
        )
        assert order.venue_order_id == "venue_123"

    def test_update_status_unknown_order_returns_none(self):
        store = OrderStore()
        assert store.update_status("missing", OrderStatus.SUBMITTED) is None


class TestApplyFill:
    def test_apply_fill_updates_filled_quantity_and_avg_price(self):
        store = OrderStore()
        order = _make_order(quantity=Decimal("10"), status=OrderStatus.SUBMITTED)
        store.add_order(order)

        fill = _make_fill(order.order_id, quantity=Decimal("3"), price=Decimal("100"))
        result = store.apply_fill(fill)

        assert result is order
        assert order.filled_quantity == Decimal("3")
        assert order.avg_fill_price == Decimal("100")

    def test_apply_fill_multiple_updates_avg_price_correctly(self):
        store = OrderStore()
        order = _make_order(quantity=Decimal("10"), status=OrderStatus.SUBMITTED)
        store.add_order(order)

        store.apply_fill(_make_fill(order.order_id, quantity=Decimal("2"), price=Decimal("100")))
        store.apply_fill(_make_fill(order.order_id, quantity=Decimal("3"), price=Decimal("110")))

        assert order.filled_quantity == Decimal("5")
        expected_avg = (Decimal("100") * Decimal("2") + Decimal("110") * Decimal("3")) / Decimal("5")
        assert order.avg_fill_price == expected_avg

    def test_apply_fill_fully_filled_sets_status_filled(self):
        store = OrderStore()
        order = _make_order(quantity=Decimal("10"), status=OrderStatus.SUBMITTED)
        store.add_order(order)

        fill = _make_fill(order.order_id, quantity=Decimal("10"), price=Decimal("100"))
        store.apply_fill(fill)

        assert order.status == OrderStatus.FILLED

    def test_apply_fill_partial_sets_status_partially_filled(self):
        store = OrderStore()
        order = _make_order(quantity=Decimal("10"), status=OrderStatus.SUBMITTED)
        store.add_order(order)

        fill = _make_fill(order.order_id, quantity=Decimal("4"), price=Decimal("100"))
        store.apply_fill(fill)

        assert order.status == OrderStatus.PARTIALLY_FILLED

    def test_apply_fill_unknown_order_returns_none(self):
        store = OrderStore()
        fill = _make_fill("unknown_order")
        assert store.apply_fill(fill) is None


class TestQueries:
    def test_get_active_orders_no_filter(self):
        store = OrderStore()
        active = _make_order(status=OrderStatus.SUBMITTED)
        terminal = _make_order(status=OrderStatus.FILLED)
        store.add_order(active)
        store.add_order(terminal)

        result = store.get_active_orders()
        assert len(result) == 1
        assert result[0] is active

    def test_get_active_orders_filter_by_instrument(self):
        store = OrderStore()
        o1 = _make_order(instrument_id="BTC.binance.crypto", status=OrderStatus.SUBMITTED)
        o2 = _make_order(instrument_id="ETH.binance.crypto", status=OrderStatus.SUBMITTED)
        store.add_order(o1)
        store.add_order(o2)

        result = store.get_active_orders(instrument_id="BTC.binance.crypto")
        assert len(result) == 1
        assert result[0] is o1

    def test_get_orders_by_strategy(self):
        store = OrderStore()
        o1 = _make_order(strategy_id="alpha")
        o2 = _make_order(strategy_id="beta")
        o3 = _make_order(strategy_id="alpha")
        store.add_order(o1)
        store.add_order(o2)
        store.add_order(o3)

        result = store.get_orders_by_strategy("alpha")
        assert len(result) == 2
        assert o1 in result
        assert o3 in result

    def test_get_all_orders(self):
        store = OrderStore()
        o1 = _make_order()
        o2 = _make_order()
        store.add_order(o1)
        store.add_order(o2)

        assert len(store.get_all_orders()) == 2


class TestCounts:
    def test_active_count_and_total_count(self):
        store = OrderStore()
        assert store.active_count == 0
        assert store.total_count == 0

        store.add_order(_make_order(status=OrderStatus.SUBMITTED))
        store.add_order(_make_order(status=OrderStatus.FILLED))
        store.add_order(_make_order(status=OrderStatus.PARTIALLY_FILLED))

        assert store.total_count == 3
        assert store.active_count == 2


class TestThreadSafety:
    def test_concurrent_add_and_update_no_crash(self):
        store = OrderStore()
        orders = [_make_order(status=OrderStatus.NEW) for _ in range(100)]

        def add_orders():
            for o in orders:
                store.add_order(o)

        def update_orders():
            for o in orders:
                store.update_status(o.order_id, OrderStatus.PENDING_SUBMIT)
                store.update_status(o.order_id, OrderStatus.SUBMITTED)

        t1 = threading.Thread(target=add_orders)
        t2 = threading.Thread(target=update_orders)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert store.total_count == 100

    def test_concurrent_apply_fill_no_crash(self):
        store = OrderStore()
        order = _make_order(quantity=Decimal("1000"), status=OrderStatus.SUBMITTED)
        store.add_order(order)

        def apply_fills():
            for _ in range(50):
                fill = _make_fill(order.order_id, quantity=Decimal("1"), price=Decimal("100"))
                store.apply_fill(fill)

        threads = [threading.Thread(target=apply_fills) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert order.filled_quantity == Decimal("200")
        assert order.status == OrderStatus.PARTIALLY_FILLED
