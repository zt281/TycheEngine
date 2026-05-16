"""Static Data Module configuration."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StaticDataConfig:
    """Configuration for Static Data module.

    Controls OpenCTP DataCenter API endpoint, refresh intervals,
    local storage path, and filter criteria for China futures/options.
    """

    # OpenCTP DataCenter base URL
    base_url: str = "http://dict.openctp.cn"

    # Refresh interval in seconds (default: 6 hours)
    refresh_interval: int = 21600

    # Local storage directory for static data files
    data_dir: str = "data/static"

    # Engine connection
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555

    # Filter: areas to fetch (default China only)
    areas: List[str] = field(default_factory=lambda: ["China"])

    # Filter: instrument types to fetch
    types: List[str] = field(default_factory=lambda: ["futures", "option"])

    # Filter: specific markets (empty = all)
    markets: List[str] = field(default_factory=list)

    # Filter: specific products (empty = all)
    products: List[str] = field(default_factory=list)

    # Filter: specific instruments (empty = all)
    instruments: List[str] = field(default_factory=list)

    # HTTP request timeout in seconds
    request_timeout: int = 30

    # Retry count for failed requests
    retry_count: int = 3

    # Retry delay in seconds
    retry_delay: int = 5
