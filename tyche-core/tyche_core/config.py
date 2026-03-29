"""Configuration loading for tyche-core."""

import json
from typing import Dict, Any


DEFAULT_CONFIG = {
    "nexus": {
        "endpoint": "ipc:///tmp/tyche/nexus.sock",
        "cpu_core": 0,
        "heartbeat_interval_ms": 1000,
        "heartbeat_timeout_ms": 3000,
    },
    "bus": {
        "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
        "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
        "cpu_core": 1,
        "high_water_mark": 10000,
    },
    "launcher": {
        "enabled": False,
        "config_path": "launcher-config.json",
    },
}


def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from JSON file.

    Args:
        path: Path to config file.

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file is invalid JSON.
    """
    with open(path) as f:
        return json.load(f)


def load_config_with_defaults(path: str) -> Dict[str, Any]:
    """Load configuration with defaults for missing values."""
    config = load_config(path)
    merged = _deep_merge(DEFAULT_CONFIG, config)
    return merged


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
