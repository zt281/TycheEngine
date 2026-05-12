"""Tyche event name constants - source of truth for topic names.

Naming convention (v3):
- Underscored bare event-type names: quote, trade, bar, order_submit, etc.
- NO dots in event names
- NO parameterization (instrument_id goes in payload)
- NO streaming_ prefix (dropped per D-03)

Keep src/modules/trading/events.py for trading-specific constants only.
"""

# --- Market Data Events ---

QUOTE = "quote"
TRADE = "trade"
BAR = "bar"
ORDER_BOOK = "orderbook"

# --- Order Flow Events ---

ORDER_SUBMIT = "order_submit"
ORDER_APPROVED = "order_approved"
ORDER_REJECTED = "order_rejected"
ORDER_EXECUTE = "order_execute"
ORDER_CANCEL = "order_cancel"
ORDER_UPDATE = "order_update"

# --- Fill Events ---

FILL = "fill"

# --- Portfolio Events ---

POSITION_UPDATE = "position_update"
ACCOUNT_UPDATE = "account_update"

# --- Risk Events ---

RISK_ALERT = "risk_alert"

# --- System Events ---

SYSTEM_CLOCK = "system_clock"
SYSTEM_SHUTDOWN = "system_shutdown"
