"""Configurable risk rules for pre-trade validation."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from tyche.trading.models.order import Order
from tyche.trading.models.position import Position

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    """Result of a risk rule check."""

    passed: bool
    rule_name: str
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "rule_name": self.rule_name,
            "reason": self.reason,
        }


class RiskRule(ABC):
    """Abstract base for risk rules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Rule name for identification."""
        ...

    @abstractmethod
    def check(self, order: Order, context: "RiskContext") -> RiskCheckResult:
        """Evaluate the order against this rule.

        Args:
            order: The order to validate.
            context: Current risk state (positions, daily P&L, etc.)

        Returns:
            RiskCheckResult indicating pass/fail with reason.
        """
        ...


@dataclass
class RiskContext:
    """Shared state for risk rule evaluation."""

    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: Decimal = Decimal("0")
    daily_volume: Decimal = Decimal("0")
    order_count_today: int = 0
    last_order_time: float = 0.0


class MaxPositionSizeRule(RiskRule):
    """Reject orders that would exceed max position size per instrument."""

    def __init__(self, max_size: Decimal):
        self._max_size = max_size

    @property
    def name(self) -> str:
        return "max_position_size"

    def check(self, order: Order, context: RiskContext) -> RiskCheckResult:
        position = context.positions.get(order.instrument_id)
        current_qty = position.quantity if position else Decimal("0")
        projected = current_qty + order.quantity

        if projected > self._max_size:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Position would exceed max size: {projected} > {self._max_size}",
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxOrderValueRule(RiskRule):
    """Reject orders exceeding a maximum notional value."""

    def __init__(self, max_value: Decimal):
        self._max_value = max_value

    @property
    def name(self) -> str:
        return "max_order_value"

    def check(self, order: Order, context: RiskContext) -> RiskCheckResult:
        price = order.price or Decimal("0")
        if price == Decimal("0"):
            # Market order - can't check notional without price
            return RiskCheckResult(passed=True, rule_name=self.name)

        notional = order.quantity * price
        if notional > self._max_value:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Order value {notional} exceeds max {self._max_value}",
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class MaxDailyLossRule(RiskRule):
    """Reject all orders if daily loss exceeds threshold."""

    def __init__(self, max_loss: Decimal):
        self._max_loss = max_loss  # Positive value representing max acceptable loss

    @property
    def name(self) -> str:
        return "max_daily_loss"

    def check(self, order: Order, context: RiskContext) -> RiskCheckResult:
        if context.daily_pnl < -self._max_loss:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Daily loss {context.daily_pnl} exceeds max {-self._max_loss}",
            )
        return RiskCheckResult(passed=True, rule_name=self.name)


class RateLimitRule(RiskRule):
    """Limit order submission rate."""

    def __init__(self, min_interval_seconds: float = 0.1, max_orders_per_minute: int = 60):
        self._min_interval = min_interval_seconds
        self._max_per_minute = max_orders_per_minute

    @property
    def name(self) -> str:
        return "rate_limit"

    def check(self, order: Order, context: RiskContext) -> RiskCheckResult:
        now = time.time()
        if context.last_order_time > 0:
            elapsed = now - context.last_order_time
            if elapsed < self._min_interval:
                return RiskCheckResult(
                    passed=False,
                    rule_name=self.name,
                    reason=f"Order too fast: {elapsed:.3f}s < min {self._min_interval}s",
                )
        return RiskCheckResult(passed=True, rule_name=self.name)


class RiskRuleEngine:
    """Evaluates all configured risk rules against an order.

    All rules must pass for an order to be approved.
    """

    def __init__(self, rules: Optional[List[RiskRule]] = None):
        self._rules: List[RiskRule] = rules or []

    def add_rule(self, rule: RiskRule) -> None:
        """Add a risk rule to the engine."""
        self._rules.append(rule)

    def evaluate(self, order: Order, context: RiskContext) -> List[RiskCheckResult]:
        """Evaluate all rules against the order.

        Returns:
            List of all check results. Order is approved only if all pass.
        """
        results: List[RiskCheckResult] = []
        for rule in self._rules:
            try:
                result = rule.check(order, context)
                results.append(result)
            except Exception as e:
                logger.error("Risk rule %s raised exception: %s", rule.name, e)
                results.append(
                    RiskCheckResult(passed=False, rule_name=rule.name, reason=f"Exception: {e}")
                )
        return results

    def is_approved(self, results: List[RiskCheckResult]) -> bool:
        """Check if all results passed."""
        return all(r.passed for r in results)
