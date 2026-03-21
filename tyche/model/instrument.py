# tyche/model/instrument.py
from dataclasses import dataclass, field
from tyche.model.enums import AssetClass


@dataclass
class Instrument:
    """Full instrument descriptor. InstrumentId is the compact 64-bit encoding."""
    symbol: str
    asset_class: AssetClass
    venue: str
    description: str = ""
    lot_size: float = 1.0
    tick_size: float = 0.01
    currency: str = "USD"
