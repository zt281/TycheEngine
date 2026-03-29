"""Unit tests for tyche_core.bus module."""

import pytest
import zmq
import threading
import time


def test_bus_creation():
    from tyche_core.bus import Bus

    bus = Bus(
        xsub_endpoint="inproc://test_xsub",
        xpub_endpoint="inproc://test_xpub"
    )
    assert bus.xsub_endpoint == "inproc://test_xsub"
    assert bus.xpub_endpoint == "inproc://test_xpub"


def test_bus_default_high_water_mark():
    from tyche_core.bus import Bus

    bus = Bus(
        xsub_endpoint="inproc://test_xsub2",
        xpub_endpoint="inproc://test_xpub2"
    )
    assert bus.high_water_mark == 10000


def test_bus_custom_high_water_mark():
    from tyche_core.bus import Bus

    bus = Bus(
        xsub_endpoint="inproc://test_xsub3",
        xpub_endpoint="inproc://test_xpub3",
        high_water_mark=5000
    )
    assert bus.high_water_mark == 5000


def test_bus_get_dropped_messages_initially_zero():
    from tyche_core.bus import Bus

    bus = Bus(
        xsub_endpoint="inproc://test_xsub4",
        xpub_endpoint="inproc://test_xpub4"
    )
    assert bus.get_dropped_messages() == 0


def test_bus_starts_and_stops():
    from tyche_core.bus import Bus

    bus = Bus(
        xsub_endpoint="inproc://test_xsub5",
        xpub_endpoint="inproc://test_xpub5"
    )
    bus.start()
    time.sleep(0.1)
    assert bus._running is True
    bus.stop()
    time.sleep(0.1)
    assert bus._running is False


# Message forwarding is tested in integration tests (Task 16)
# def test_bus_forwards_messages():
