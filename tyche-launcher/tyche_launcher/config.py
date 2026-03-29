"""Launcher config loading."""

import json
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ModuleConfig:
    """Configuration for a single module."""
    name: str
    command: List[str]
    restart_policy: str  # "never", "always", "on-failure"
    max_restarts: int = 3
    restart_window_seconds: int = 60
    cpu_core: int = -1  # -1 means no affinity
    environment: Dict[str, str] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}


@dataclass
class LauncherConfig:
    """Configuration for the launcher."""
    nexus_endpoint: str
    poll_interval_ms: int = 1000
    modules: List[ModuleConfig] = None

    def __post_init__(self):
        if self.modules is None:
            self.modules = []


def load_launcher_config(path: str) -> LauncherConfig:
    """Load launcher configuration from JSON file.

    Args:
        path: Path to config file.

    Returns:
        LauncherConfig instance.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file is invalid JSON.
    """
    with open(path) as f:
        data = json.load(f)

    modules = []
    for mod_data in data.get("modules", []):
        modules.append(ModuleConfig(
            name=mod_data["name"],
            command=mod_data["command"],
            restart_policy=mod_data.get("restart_policy", "never"),
            max_restarts=mod_data.get("max_restarts", 3),
            restart_window_seconds=mod_data.get("restart_window_seconds", 60),
            cpu_core=mod_data.get("cpu_core", -1),
            environment=mod_data.get("environment", {}),
        ))

    return LauncherConfig(
        nexus_endpoint=data["nexus_endpoint"],
        poll_interval_ms=data.get("poll_interval_ms", 1000),
        modules=modules,
    )
