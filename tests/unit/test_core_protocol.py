"""Unit tests for tyche_core.protocol constants."""

import pytest


def test_message_types_are_bytes():
    from tyche_core.protocol import READY, ACK, HB, CMD, REPLY, DISCO

    assert isinstance(READY, bytes), "READY must be bytes"
    assert isinstance(ACK, bytes), "ACK must be bytes"
    assert isinstance(HB, bytes), "HB must be bytes"
    assert isinstance(CMD, bytes), "CMD must be bytes"
    assert isinstance(REPLY, bytes), "REPLY must be bytes"
    assert isinstance(DISCO, bytes), "DISCO must be bytes"


def test_command_types_are_bytes():
    from tyche_core.protocol import CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS

    assert isinstance(CMD_START, bytes), "CMD_START must be bytes"
    assert isinstance(CMD_STOP, bytes), "CMD_STOP must be bytes"
    assert isinstance(CMD_RECONFIGURE, bytes), "CMD_RECONFIGURE must be bytes"
    assert isinstance(CMD_STATUS, bytes), "CMD_STATUS must be bytes"


def test_status_codes_are_bytes():
    from tyche_core.protocol import STATUS_OK, STATUS_ERROR

    assert isinstance(STATUS_OK, bytes), "STATUS_OK must be bytes"
    assert isinstance(STATUS_ERROR, bytes), "STATUS_ERROR must be bytes"


def test_protocol_version_is_int():
    from tyche_core.protocol import PROTOCOL_VERSION

    assert isinstance(PROTOCOL_VERSION, int), "PROTOCOL_VERSION must be int"
    assert PROTOCOL_VERSION == 1


def test_default_timeouts_are_ints():
    from tyche_core.protocol import (
        DEFAULT_HEARTBEAT_INTERVAL_MS,
        DEFAULT_REGISTRATION_TIMEOUT_MS,
        HEARTBEAT_TIMEOUT_MULTIPLIER,
    )

    assert isinstance(DEFAULT_HEARTBEAT_INTERVAL_MS, int)
    assert isinstance(DEFAULT_REGISTRATION_TIMEOUT_MS, int)
    assert isinstance(HEARTBEAT_TIMEOUT_MULTIPLIER, int)
    assert HEARTBEAT_TIMEOUT_MULTIPLIER == 3
