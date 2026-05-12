"""Unit tests for RiskRule and RiskRuleEngine."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from modules.trading.models.enums import OrderType, Side
from modules.trading.models.order import Order
from modules.trading.models.position import Position
from modules.trading.risk.rules import (
    MaxDailyLossRule,
    MaxOrderValueRule,
    MaxPositionSizeRule,
    RateLimitRule,
    RiskCheckResult,
    RiskContext,
    RiskRuleEngine,
)


@pytest.fixture
def order():
    return Order(
        instrument_id="BTC-USD",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("5"),
        price=Decimal("100"),
    )


@pytest.fixture
def context():
    return RiskContext()


class TestMaxPositionSizeRule:
    """Tests for MaxPositionSizeRule."""

    def test_passes_when_under_limit(self, order, context):
        rule = MaxPositionSizeRule(max_size=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is True
        assert result.rule_name == "max_position_size"

    def test_fails_when_projected_exceeds_limit(self, order, context):
        context.positions["BTC-USD"] = Position(
            instrument_id="BTC-USD",
            quantity=Decimal("998"),
        )
        rule = MaxPositionSizeRule(max_size=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is False
        assert "exceed max size" in result.reason


class TestMaxOrderValueRule:
    """Tests for MaxOrderValueRule."""

    def test_passes_when_under_limit(self, order, context):
        rule = MaxOrderValueRule(max_value=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is True

    def test_fails_when_notional_exceeds_limit(self, order, context):
        rule = MaxOrderValueRule(max_value=Decimal("100"))
        result = rule.check(order, context)
        assert result.passed is False
        assert "exceeds max" in result.reason

    def test_passes_for_market_order_with_zero_price(self, order, context):
        order.order_type = OrderType.MARKET
        order.price = None
        rule = MaxOrderValueRule(max_value=Decimal("1"))
        result = rule.check(order, context)
        assert result.passed is True


class TestMaxDailyLossRule:
    """Tests for MaxDailyLossRule."""

    def test_passes_when_daily_pnl_above_negative_limit(self, order, context):
        rule = MaxDailyLossRule(max_loss=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is True

    def test_fails_when_daily_pnl_below_negative_limit(self, order, context):
        context.daily_pnl = Decimal("-1500")
        rule = MaxDailyLossRule(max_loss=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is False
        assert "Daily loss" in result.reason

    def test_passes_when_daily_pnl_exactly_at_negative_limit(self, order, context):
        context.daily_pnl = Decimal("-1000")
        rule = MaxDailyLossRule(max_loss=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is True


class TestRateLimitRule:
    """Tests for RateLimitRule."""

    def test_passes_when_interval_sufficient(self, order, context):
        import time

        context.last_order_time = time.time() - 1.0
        rule = RateLimitRule(min_interval_seconds=0.1)
        result = rule.check(order, context)
        assert result.passed is True

    def test_fails_when_too_fast(self, order, context):
        import time

        context.last_order_time = time.time()
        rule = RateLimitRule(min_interval_seconds=1.0)
        result = rule.check(order, context)
        assert result.passed is False
        assert "too fast" in result.reason

    def test_passes_when_no_previous_order(self, order, context):
        context.last_order_time = 0.0
        rule = RateLimitRule(min_interval_seconds=1.0)
        result = rule.check(order, context)
        assert result.passed is True


class TestRiskRuleEngine:
    """Tests for RiskRuleEngine."""

    def test_evaluate_returns_results_for_all_rules(self, order, context):
        engine = RiskRuleEngine(
            rules=[
                MaxPositionSizeRule(max_size=Decimal("1000")),
                MaxOrderValueRule(max_value=Decimal("1000")),
            ]
        )
        results = engine.evaluate(order, context)
        assert len(results) == 2
        assert all(isinstance(r, RiskCheckResult) for r in results)

    def test_is_approved_true_when_all_pass(self, order, context):
        engine = RiskRuleEngine(
            rules=[
                MaxPositionSizeRule(max_size=Decimal("1000")),
                MaxOrderValueRule(max_value=Decimal("1000")),
            ]
        )
        results = engine.evaluate(order, context)
        assert engine.is_approved(results) is True

    def test_is_approved_false_when_any_fails(self, order, context):
        engine = RiskRuleEngine(
            rules=[
                MaxPositionSizeRule(max_size=Decimal("1000")),
                MaxOrderValueRule(max_value=Decimal("1")),
            ]
        )
        results = engine.evaluate(order, context)
        assert engine.is_approved(results) is False

    def test_exception_in_rule_returns_failed_result(self, order, context):
        bad_rule = MagicMock()
        bad_rule.name = "bad_rule"
        bad_rule.check.side_effect = RuntimeError("boom")

        engine = RiskRuleEngine(rules=[bad_rule])
        results = engine.evaluate(order, context)
        assert len(results) == 1
        assert results[0].passed is False
        assert "Exception: boom" in results[0].reason

    def test_add_rule_appends_to_rules(self, order, context):
        engine = RiskRuleEngine()
        engine.add_rule(MaxPositionSizeRule(max_size=Decimal("1000")))
        results = engine.evaluate(order, context)
        assert len(results) == 1
        assert results[0].passed is True


class TestRiskContext:
    """Tests for RiskContext defaults and updates."""

    def test_default_values(self):
        ctx = RiskContext()
        assert ctx.positions == {}
        assert ctx.daily_pnl == Decimal("0")
        assert ctx.daily_volume == Decimal("0")
        assert ctx.order_count_today == 0
        assert ctx.last_order_time == 0.0

    def test_position_updates(self):
        ctx = RiskContext()
        ctx.positions["BTC-USD"] = Position(
            instrument_id="BTC-USD",
            quantity=Decimal("10"),
        )
        assert ctx.positions["BTC-USD"].quantity == Decimal("10")
