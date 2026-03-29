"""Socket address helper for IPC endpoints."""

import sys


_ENDPOINTS = {
    "nexus": {
        "linux": "ipc:///tmp/tyche/nexus.sock",
        "win32": "ipc://tyche-nexus",
    },
    "bus_xsub": {
        "linux": "ipc:///tmp/tyche/bus_xsub.sock",
        "win32": "ipc://tyche-bus-xsub",
    },
    "bus_xpub": {
        "linux": "ipc:///tmp/tyche/bus_xpub.sock",
        "win32": "ipc://tyche-bus-xpub",
    },
}


def get_socket_address(name: str) -> str:
    """Get IPC endpoint for the given socket name.

    Args:
        name: Socket name - one of "nexus", "bus_xsub", "bus_xpub".

    Returns:
        IPC endpoint URL.

    Raises:
        ValueError: If name is not recognized.
    """
    if name not in _ENDPOINTS:
        raise ValueError(f"Unknown socket name: {name}")

    platform = sys.platform
    if platform not in _ENDPOINTS[name]:
        # Default to linux-style paths for unknown platforms
        platform = "linux"

    return _ENDPOINTS[name][platform]
