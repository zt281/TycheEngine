"""Local file storage for static data."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StaticDataStorage:
    """Manages persistence of static data to local JSON files.

    Directory layout under data_dir:
        data_dir/
            markets.json
            products.json
            instruments.json
            prices.json
            times.json
            metadata.json
    """

    CATEGORIES = ["markets", "products", "instruments", "prices", "times"]

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, category: str) -> Path:
        """Return file path for a given category."""
        return self.data_dir / f"{category}.json"

    def save(self, category: str, data: List[Dict[str, Any]]) -> None:
        """Save data for a category to disk."""
        if category not in self.CATEGORIES:
            raise ValueError(f"Unknown category: {category}")

        file_path = self._file_path(category)
        record = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(data),
            "data": data,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info("[%s] Saved %d %s records to %s",
                    self.__class__.__name__, len(data), category, file_path)

    def load(self, category: str) -> Optional[Dict[str, Any]]:
        """Load data for a category from disk.

        Returns:
            Dict with keys: updated_at, count, data
            or None if file does not exist.
        """
        if category not in self.CATEGORIES:
            raise ValueError(f"Unknown category: {category}")

        file_path = self._file_path(category)
        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_all(self) -> Dict[str, Optional[Dict[str, Any]]]:
        """Load all categories from disk."""
        return {cat: self.load(cat) for cat in self.CATEGORIES}

    def save_all(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Save all categories to disk."""
        for category in self.CATEGORIES:
            if category in data:
                self.save(category, data[category])

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata about stored data."""
        metadata = {}
        for category in self.CATEGORIES:
            record = self.load(category)
            if record:
                metadata[category] = {
                    "count": record.get("count", 0),
                    "updated_at": record.get("updated_at"),
                }
            else:
                metadata[category] = {"count": 0, "updated_at": None}
        return metadata
