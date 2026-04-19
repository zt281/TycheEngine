"""Trading enumerations for order types, sides, statuses, and venue classifications."""

from enum import Enum, auto


class Side(Enum):
    """Order/trade direction."""

    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """Supported order types."""

    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()


class OrderStatus(Enum):
    """Order lifecycle states."""

    NEW = auto()
    PENDING_SUBMIT = auto()
    SUBMITTED = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    PENDING_CANCEL = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()


class TimeInForce(Enum):
    """Order time-in-force policies."""

    GTC = auto()  # Good Till Cancel
    IOC = auto()  # Immediate Or Cancel
    FOK = auto()  # Fill Or Kill
    GTD = auto()  # Good Till Date
    DAY = auto()  # Day order


class VenueType(Enum):
    """Exchange/venue classification."""

    CRYPTO = auto()
    FUTURES = auto()
    STOCK = auto()
    FOREX = auto()
    OPTIONS = auto()


class AssetClass(Enum):
    """Broad asset class categorization."""

    CRYPTO = auto()
    EQUITY = auto()
    FUTURES = auto()
    FOREX = auto()
    OPTIONS = auto()
    BOND = auto()


class PositionSide(Enum):
    """Position direction."""

    LONG = auto()
    SHORT = auto()
    FLAT = auto()
