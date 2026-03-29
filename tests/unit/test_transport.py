"""Unit tests for tyche_client.transport socket address helper."""

import pytest
import sys


def test_get_socket_address_nexus_linux():
    """Nexus endpoint on Linux."""
    from tyche_client.transport import get_socket_address

    # Mock Linux platform
    original_platform = sys.platform
    try:
        sys.platform = "linux"
        # Need to reimport to get Linux endpoints
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
        from tyche_client.transport import get_socket_address

        addr = get_socket_address("nexus")
        assert addr == "ipc:///tmp/tyche/nexus.sock"
    finally:
        sys.platform = original_platform
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)


def test_get_socket_address_bus_xsub_linux():
    """Bus XSUB endpoint on Linux."""
    from tyche_client.transport import get_socket_address

    original_platform = sys.platform
    try:
        sys.platform = "linux"
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
        from tyche_client.transport import get_socket_address

        addr = get_socket_address("bus_xsub")
        assert addr == "ipc:///tmp/tyche/bus_xsub.sock"
    finally:
        sys.platform = original_platform
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)


def test_get_socket_address_bus_xpub_linux():
    """Bus XPUB endpoint on Linux."""
    from tyche_client.transport import get_socket_address

    original_platform = sys.platform
    try:
        sys.platform = "linux"
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
        from tyche_client.transport import get_socket_address

        addr = get_socket_address("bus_xpub")
        assert addr == "ipc:///tmp/tyche/bus_xpub.sock"
    finally:
        sys.platform = original_platform
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)


def test_get_socket_address_nexus_windows():
    """Nexus endpoint on Windows."""
    from tyche_client.transport import get_socket_address

    original_platform = sys.platform
    try:
        sys.platform = "win32"
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
        from tyche_client.transport import get_socket_address

        addr = get_socket_address("nexus")
        assert addr == "ipc://tyche-nexus"
    finally:
        sys.platform = original_platform
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)


def test_get_socket_address_unknown_raises():
    """Unknown socket name raises ValueError."""
    from tyche_client.transport import get_socket_address

    original_platform = sys.platform
    try:
        sys.platform = "linux"
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
        from tyche_client.transport import get_socket_address

        with pytest.raises(ValueError, match="Unknown socket name"):
            get_socket_address("unknown")
    finally:
        sys.platform = original_platform
        import importlib
        import tyche_client.transport
        importlib.reload(tyche_client.transport)
