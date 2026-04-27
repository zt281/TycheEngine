"""End-to-end integration test for the trading pipeline.

Wires together StrategyContext, RiskModule, OMSModule, SimulatedGateway,
and PortfolioModule without real ZMQ by calling handlers directly.
"""

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from modules.trading import events
from modules.trading.gateway.simulated import SimulatedGateway
from modules.trading.models.enums import OrderStatus, Side
from modules.trading.models.order import Order
from modules.trading.oms.module import OMSModule
from modules.trading.portfolio.module import PortfolioModule
from modules.trading.risk.module import RiskModule
from modules.trading.risk.rules import MaxPositionSizeRule
from modules.trading.strategy.context import StrategyContext
from tyche.types import Endpoint


@pytest.fixture
def mock_endpoint() -> Endpoint:
    """Return a dummy endpoint for module construction."""
    return Endpoint(host="127.0.0.1", port=5555)


@pytest.fixture
def captured_events() -> List[Dict[str, Any]]:
    """Shared list to capture events sent by modules."""
    return []


@pytest.fixture
def risk_module(mock_endpoint: Endpoint, captured_events: List[Dict[str, Any]]) -> RiskModule:
    """Create a RiskModule with a permissive rule engine."""
    module = RiskModule(
        engine_endpoint=mock_endpoint,
        rules=[MaxPositionSizeRule(max_size=Decimal("100"))],
    )
    _patch_send_event(module, captured_events)
    return module


@pytest.fixture
def oms_module(mock_endpoint: Endpoint, captured_events: List[Dict[str, Any]]) -> OMSModule:
    """Create an OMSModule with patched send_event."""
    module = OMSModule(engine_endpoint=mock_endpoint)
    _patch_send_event(module, captured_events)
    return module


@pytest.fixture
def portfolio_module(mock_endpoint: Endpoint, captured_events: List[Dict[str, Any]]) -> PortfolioModule:
    """Create a PortfolioModule with patched send_event."""
    module = PortfolioModule(engine_endpoint=mock_endpoint)
    _patch_send_event(module, captured_events)
    return module


@pytest.fixture
def gateway(mock_endpoint: Endpoint, captured_events: List[Dict[str, Any]]) -> SimulatedGateway:
    """Create a SimulatedGateway with patched send_event."""
    module = SimulatedGateway(
        engine_endpoint=mock_endpoint,
        instruments=["BTCUSDT.simulated.crypto"],
        base_prices={"BTCUSDT.simulated.crypto": Decimal("65000.00")},
        fill_probability=1.0,
    )
    _patch_send_event(module, captured_events)
    return module


@pytest.fixture
def strategy_context(captured_events: List[Dict[str, Any]]) -> StrategyContext:
    """Create a StrategyContext that appends to captured_events."""

    def send_event_fn(event: str, payload: Dict[str, Any]) -> None:
        captured_events.append({"event": event, "payload": payload})

    return StrategyContext(strategy_id="test_strategy", send_event_fn=send_event_fn)


def _patch_send_event(module: Any, captured_events: List[Dict[str, Any]]) -> None:
    """Patch send_event on a module to capture events instead of using ZMQ."""

    def capture(event: str, payload: Dict[str, Any], recipient: Any = None) -> None:
        captured_events.append({"event": event, "payload": payload})

    module.send_event = capture


def _run_pipeline_order_submit(
    strategy_context: StrategyContext,
    risk_module: RiskModule,
    oms_module: OMSModule,
    gateway: SimulatedGateway,
    portfolio_module: PortfolioModule,
    captured_events: List[Dict[str, Any]],
    instrument_id: str = "BTCUSDT.simulated.crypto",
    side: Side = Side.BUY,
    quantity: Decimal = Decimal("0.5"),
) -> Order:
    """Simulate the full pipeline for a single order submission.

    Returns the Order object created by the strategy.
    """
    # 1. Strategy submits order
    order = strategy_context.submit_order(
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
    )

    # Extract the ORDER_SUBMIT event and feed it to Risk
    submit_event = next(e for e in captured_events if e["event"] == events.ORDER_SUBMIT)
    risk_result = risk_module._handle_order_submit(submit_event["payload"])

    # If approved, feed ORDER_APPROVED to OMS
    if risk_result.get("approved"):
        approved_event = next(e for e in captured_events if e["event"] == events.ORDER_APPROVED)
        oms_module._handle_order_approved(approved_event["payload"])

        # OMS sends ack_order_execute_simulated -> gateway handles it
        execute_event = next(e for e in captured_events if e["event"] == "ack_order_execute_simulated")
        gateway._handle_order_execute(execute_event["payload"])

        # Gateway publishes fill and order update
        # Fill is captured in events; feed it to OMS and Portfolio
        fill_events = [e for e in captured_events if e["event"] == events.fill_event(instrument_id)]
        for fe in fill_events:
            oms_module._handle_fill(fe["payload"])
            portfolio_module._handle_fill(fe["payload"])

    return order


class TestFullPipelineSingleOrder:
    """Test a single order flowing through the entire pipeline."""

    @patch("modules.trading.gateway.simulated.random.random", return_value=0.0)
    @patch("modules.trading.gateway.simulated.time.sleep")
    def test_risk_approves_gateway_fills(
        self,
        mock_sleep: Any,
        mock_random: Any,
        strategy_context: StrategyContext,
        risk_module: RiskModule,
        oms_module: OMSModule,
        gateway: SimulatedGateway,
        portfolio_module: PortfolioModule,
        captured_events: List[Dict[str, Any]],
    ) -> None:
        """Risk approves order -> Gateway fills -> OMS updates -> Portfolio has position."""
        order = _run_pipeline_order_submit(
            strategy_context,
            risk_module,
            oms_module,
            gateway,
            portfolio_module,
            captured_events,
        )

        # Verify OMS has the order and it is FILLED
        oms_order = oms_module.order_store.get_order(order.order_id)
        assert oms_order is not None
        assert oms_order.status == OrderStatus.FILLED
        assert oms_order.filled_quantity == Decimal("0.5")

        # Verify Portfolio has a position
        position = portfolio_module.get_position("BTCUSDT.simulated.crypto")
        assert position.quantity == Decimal("0.5")

        # Verify event sequence includes key events
        event_names = [e["event"] for e in captured_events]
        assert events.ORDER_SUBMIT in event_names
        assert events.ORDER_APPROVED in event_names
        assert "ack_order_execute_simulated" in event_names
        assert events.fill_event("BTCUSDT.simulated.crypto") in event_names
        assert events.ORDER_UPDATE in event_names
        assert events.POSITION_UPDATE in event_names


class TestPipelineRiskRejects:
    """Test pipeline when Risk rejects the order."""

    def test_risk_rejects_order_oms_never_sees_it(
        self,
        strategy_context: StrategyContext,
        oms_module: OMSModule,
        portfolio_module: PortfolioModule,
        captured_events: List[Dict[str, Any]],
        mock_endpoint: Endpoint,
    ) -> None:
        """Risk rejects order -> OMS never sees it, Portfolio unchanged."""
        # Create a restrictive risk module that rejects everything
        restrictive_risk = RiskModule(
            engine_endpoint=mock_endpoint,
            rules=[MaxPositionSizeRule(max_size=Decimal("0"))],
        )
        _patch_send_event(restrictive_risk, captured_events)

        order = strategy_context.submit_order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            quantity=Decimal("0.5"),
        )

        submit_event = next(e for e in captured_events if e["event"] == events.ORDER_SUBMIT)
        risk_result = restrictive_risk._handle_order_submit(submit_event["payload"])

        assert risk_result["approved"] is False

        # OMS should not have the order
        assert oms_module.order_store.get_order(order.order_id) is None

        # Portfolio should be flat
        position = portfolio_module.get_position("BTCUSDT.simulated.crypto")
        assert position.quantity == Decimal("0")

        # Rejection event should have been published
        event_names = [e["event"] for e in captured_events]
        assert events.ORDER_REJECTED in event_names


class TestPipelineCancel:
    """Test order cancellation through the pipeline."""

    @patch("modules.trading.gateway.simulated.random.random", return_value=0.0)
    @patch("modules.trading.gateway.simulated.time.sleep")
    def test_strategy_cancels_active_order(
        self,
        mock_sleep: Any,
        mock_random: Any,
        strategy_context: StrategyContext,
        risk_module: RiskModule,
        oms_module: OMSModule,
        gateway: SimulatedGateway,
        portfolio_module: PortfolioModule,
        captured_events: List[Dict[str, Any]],
    ) -> None:
        """Strategy cancels active order -> OMS routes cancel -> Gateway cancels."""
        # Submit an order first, let gateway fill it so OMS marks it SUBMITTED,
        # then transition to a state where cancel is valid.
        # We simulate a partial fill to get SUBMITTED, then cancel.
        order = strategy_context.submit_order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            quantity=Decimal("0.5"),
        )

        # Run through risk and oms (gateway will fill)
        submit_event = next(e for e in captured_events if e["event"] == events.ORDER_SUBMIT)
        risk_result = risk_module._handle_order_submit(submit_event["payload"])
        assert risk_result["approved"] is True

        approved_event = next(e for e in captured_events if e["event"] == events.ORDER_APPROVED)
        oms_module._handle_order_approved(approved_event["payload"])

        # Simulate gateway execution (full fill for simplicity)
        execute_event = next(e for e in captured_events if e["event"] == "ack_order_execute_simulated")
        gateway._handle_order_execute(execute_event["payload"])

        # Feed fill to OMS and Portfolio
        fill_events = [e for e in captured_events if e["event"] == events.fill_event("BTCUSDT.simulated.crypto")]
        for fe in fill_events:
            oms_module._handle_fill(fe["payload"])
            portfolio_module._handle_fill(fe["payload"])

        # At this point the order is FILLED; reset to SUBMITTED for cancel test
        oms_order = oms_module.order_store.get_order(order.order_id)
        assert oms_order is not None
        oms_order.status = OrderStatus.SUBMITTED
        oms_order.filled_quantity = Decimal("0")

        # Strategy cancels the order
        strategy_context.cancel_order(order.order_id, order.instrument_id)

        cancel_event = next(e for e in captured_events if e["event"] == events.ORDER_CANCEL)
        oms_module._handle_cancel_request(cancel_event["payload"])

        # OMS should have routed cancel to gateway
        cancel_topic = "ack_order_cancel_simulated"
        cancel_to_gateway = [e for e in captured_events if e["event"] == cancel_topic]
        assert len(cancel_to_gateway) >= 1

        # Simulate gateway handling the cancel
        gateway._handle_order_cancel(cancel_to_gateway[-1]["payload"])

        # Verify OMS updated status to pending cancel (OMS sets this before routing)
        updated_oms_order = oms_module.order_store.get_order(order.order_id)
        assert updated_oms_order is not None
        assert updated_oms_order.status == OrderStatus.PENDING_CANCEL

    @patch("modules.trading.gateway.simulated.random.random", return_value=0.0)
    @patch("modules.trading.gateway.simulated.time.sleep")
    def test_cancel_after_fill_is_ignored(
        self,
        mock_sleep: Any,
        mock_random: Any,
        strategy_context: StrategyContext,
        risk_module: RiskModule,
        oms_module: OMSModule,
        gateway: SimulatedGateway,
        portfolio_module: PortfolioModule,
        captured_events: List[Dict[str, Any]],
    ) -> None:
        """Cancel on an already-filled order is ignored by OMS."""
        order = _run_pipeline_order_submit(
            strategy_context,
            risk_module,
            oms_module,
            gateway,
            portfolio_module,
            captured_events,
        )

        # Order should be filled
        assert oms_module.order_store.get_order(order.order_id).status == OrderStatus.FILLED

        # Attempt to cancel
        strategy_context.cancel_order(order.order_id, order.instrument_id)

        cancel_event = next(e for e in captured_events if e["event"] == events.ORDER_CANCEL)
        # OMS should ignore because order is not active
        oms_module._handle_cancel_request(cancel_event["payload"])

        # Status should remain FILLED
        assert oms_module.order_store.get_order(order.order_id).status == OrderStatus.FILLED
