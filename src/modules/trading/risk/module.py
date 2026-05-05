"""Risk management module - pre-trade risk gate.

Intercepts order.submit events, evaluates risk rules, and either
approves (publishes order.approved) or rejects (publishes order.rejected).
"""

import logging
import time
from typing import Any, Dict, List, Optional

from modules.trading import events
from modules.trading.models.order import Order
from modules.trading.models.position import Position
from modules.trading.risk.rules import RiskContext, RiskRule, RiskRuleEngine
from tyche.module import TycheModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class RiskModule(TycheModule):
    """Pre-trade risk management module.

    Acts as a synchronous gate for all order submissions:
    - Receives order.submit from strategies
    - Evaluates configured risk rules
    - Publishes order.approved or order.rejected

    Also listens to position.update to maintain risk context state.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        rules: Optional[List[RiskRule]] = None,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._rule_engine = RiskRuleEngine(rules=rules)
        self._risk_context = RiskContext()

    def add_rule(self, rule: RiskRule) -> None:
        """Add a risk rule at runtime."""
        self._rule_engine.add_rule(rule)

    def on_order_submit(self, payload: Dict[str, Any]) -> None:
        """Evaluate order against risk rules and publish result.

        Fire-and-forget: publishes order.approved or order.rejected event.
        """
        order = Order.from_dict(payload)
        logger.info(
            "Risk checking order: %s %s %s %s",
            order.order_id,
            order.side.name,
            order.quantity,
            order.instrument_id,
        )

        # Evaluate all rules
        results = self._rule_engine.evaluate(order, self._risk_context)
        approved = self._rule_engine.is_approved(results)

        if approved:
            logger.info("Order APPROVED: %s", order.order_id)
            # Publish approved order for OMS
            self.send_event(events.ORDER_APPROVED, payload)
            # Update risk context
            self._risk_context.order_count_today += 1
            self._risk_context.last_order_time = time.time()
        else:
            # Find first failure reason
            failed = [r for r in results if not r.passed]
            reasons = "; ".join(f"{r.rule_name}: {r.reason}" for r in failed)
            logger.warning("Order REJECTED: %s - %s", order.order_id, reasons)

            # Publish rejection
            self.send_event(
                events.ORDER_REJECTED,
                {
                    "order_id": order.order_id,
                    "instrument_id": order.instrument_id,
                    "strategy_id": order.strategy_id,
                    "reason": reasons,
                },
            )

    def on_position_update(self, payload: Dict[str, Any]) -> None:
        """Update risk context with latest position data."""
        position = Position.from_dict(payload)
        self._risk_context.positions[position.instrument_id] = position
