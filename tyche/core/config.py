# tyche/core/config.py
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class NexusAddressConfig:
    address: str
    cpu_core: int

@dataclass
class NexusPolicy:
    heartbeat_interval_ms: int = 1000
    missed_heartbeat_limit: int = 3
    registration_timeout_ms: int = 500
    registration_max_retries: int = 20
    restart_policy: str = "alert-only"

    @classmethod
    def from_file(cls, path: str) -> "NexusPolicy":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data["policy"])

@dataclass
class BusConfig:
    xsub_address: str
    xpub_address: str
    cpu_core: int
    sndhwm: int = 10000

@dataclass
class EngineConfig:
    nexus: NexusAddressConfig
    bus: BusConfig

    @classmethod
    def from_file(cls, path: str) -> "EngineConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            nexus=NexusAddressConfig(**data["nexus"]),
            bus=BusConfig(**data["bus"]),
        )

@dataclass
class ModuleConfig:
    service_name: str
    cpu_core: Optional[int] = None
    subscriptions: list = field(default_factory=list)
    nexus_address: str = "tcp://localhost:5555"
    bus_xsub: str = "tcp://localhost:5556"
    bus_xpub: str = "tcp://localhost:5557"

    @classmethod
    def from_file(cls, path: str) -> "ModuleConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data["module"]
        return cls(
            service_name=m["service_name"],
            cpu_core=m.get("cpu_core"),
            subscriptions=m.get("subscriptions", []),
            nexus_address=m.get("nexus_address", "tcp://localhost:5555"),
            bus_xsub=m.get("bus_xsub", "tcp://localhost:5556"),
            bus_xpub=m.get("bus_xpub", "tcp://localhost:5557"),
        )
