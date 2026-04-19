"""Trading event name constants and helpers.

Event naming convention:
    - Market data: quote.{instrument_id}, trade.{instrument_id}, bar.{instrument_id}.{timeframe}
    - Order flow: order.submit, order.approved, order.rejected, order.execute, order.cancel, order.update
    - Fills: fill.{instrument_id}
    - Portfolio: position.update, account.update
    - Risk: risk.alert
    - System: system.clock, system.shutdown
"""


# --- Market Data Events (published by Gateway, on_ pattern) ---

QUOTE = "quote"  # quote.{instrument_id}
TRADE = "trade"  # trade.{instrument_id}
BAR = "bar"  # bar.{instrument_id}.{timeframe}
ORDER_BOOK = "orderbook"  # orderbook.{instrument_id}


# --- Order Flow Events ---

ORDER_SUBMIT = "order.submit"  # Strategy -> Risk (ack_ pattern)
ORDER_APPROVED = "order.approved"  # Risk -> OMS (on_ pattern)
ORDER_REJECTED = "order.rejected"  # Risk -> Strategy (on_ pattern)
ORDER_EXECUTE = "order.execute"  # OMS -> Gateway (ack_ pattern)
ORDER_CANCEL = "order.cancel"  # Strategy/OMS -> Gateway (ack_ pattern)
ORDER_UPDATE = "order.update"  # OMS -> Strategy, Portfolio (on_ pattern)


# --- Fill Events ---

FILL = "fill"  # fill.{instrument_id} - Gateway -> OMS, Portfolio


# --- Portfolio Events (on_common_ broadcast pattern) ---

POSITION_UPDATE = "position.update"  # Portfolio -> Strategy, Risk
ACCOUNT_UPDATE = "account.update"  # Portfolio -> Strategy, Risk


# --- Risk Events (on_common_ broadcast pattern) ---

RISK_ALERT = "risk.alert"  # Risk -> Strategy, OMS


# --- System Events (on_common_ broadcast pattern) ---

SYSTEM_CLOCK = "system.clock"  # Clock -> All
SYSTEM_SHUTDOWN = "system.shutdown"  # Engine -> All


# --- Helper functions ---


def quote_event(instrument_id: str) -> str:
    """Build quote event topic for an instrument."""
    return f"{QUOTE}.{instrument_id}"


def trade_event(instrument_id: str) -> str:
    """Build trade event topic for an instrument."""
    return f"{TRADE}.{instrument_id}"


def bar_event(instrument_id: str, timeframe: str) -> str:
    """Build bar event topic for an instrument and timeframe."""
    return f"{BAR}.{instrument_id}.{timeframe}"


def orderbook_event(instrument_id: str) -> str:
    """Build order book event topic for an instrument."""
    return f"{ORDER_BOOK}.{instrument_id}"


def fill_event(instrument_id: str) -> str:
    """Build fill event topic for an instrument."""
    return f"{FILL}.{instrument_id}"
