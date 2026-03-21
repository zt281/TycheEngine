# tyche/utils/topics.py
import re
import tyche_core
from tyche.model.enums import BarInterval

_VALID_TOPIC_RE = re.compile(r'^[A-Z0-9_\-]+(\.[A-Z0-9_\-]+)*$')


def normalise_symbol(raw: str) -> str:
    """Normalise symbol to alphanumeric + hyphen + underscore.
    - Slashes removed (EUR/USD → EURUSD)
    - Spaces replaced with underscore
    - Dashes between digits removed (date separators: 2025-01-17 → 20250117)
    """
    s = raw.replace("/", "")
    s = s.replace(" ", "_")
    # Remove dashes between digit characters (non-overlapping, applied repeatedly)
    while re.search(r'\d-\d', s):
        s = re.sub(r'(\d)-(\d)', r'\1\2', s)
    return s


def suffix_to_bar_interval(suffix: str) -> BarInterval:
    """Convert a topic suffix string (e.g. 'M5') to a BarInterval enum value."""
    return tyche_core.bar_interval_from_suffix(suffix)


class TopicBuilder:
    @staticmethod
    def tick(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.TICK"

    @staticmethod
    def quote(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.QUOTE"

    @staticmethod
    def trade(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.TRADE"

    @staticmethod
    def bar(asset_class: str, venue: str, symbol: str, interval: BarInterval) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.BAR.{interval.topic_suffix}"

    @staticmethod
    def internal(subsystem: str, event: str) -> str:
        return f"INTERNAL.{subsystem}.{event}"

    @staticmethod
    def ctrl(source: str, event: str) -> str:
        return f"CTRL.{source}.{event}"


class TopicValidator:
    @staticmethod
    def validate(topic: str) -> None:
        """Raise ValueError if topic contains invalid characters."""
        if not _VALID_TOPIC_RE.match(topic):
            raise ValueError(
                f"Invalid topic '{topic}': must match {_VALID_TOPIC_RE.pattern}")
