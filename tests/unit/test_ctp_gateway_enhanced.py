"""Tests for enhanced CTP gateway features: state machine, errors, positions."""
import sys
from unittest.mock import MagicMock, patch

_mock_mdapi = MagicMock()
_mock_tdapi = MagicMock()
_mock_ctp = MagicMock()
_mock_ctp.mdapi = _mock_mdapi
_mock_ctp.tdapi = _mock_tdapi
sys.modules["openctp_ctp"] = _mock_ctp
sys.modules["openctp_ctp.mdapi"] = _mock_mdapi
sys.modules["openctp_ctp.tdapi"] = _mock_tdapi

# Provide real base classes for SPIs so inner classes are concrete
_mock_mdapi.CThostFtdcMdSpi = object
_mock_tdapi.CThostFtdcTraderSpi = object

import pytest
from modules.trading.gateway.ctp.gateway import CtpGateway
from modules.trading.gateway.ctp.state_machine import ConnectionState
from tyche.types import Endpoint

EP = Endpoint("127.0.0.1", 15555)


@pytest.fixture()
def gateway():
    gw = CtpGateway(
        engine_endpoint=EP,
        venue_name="openctp",
        broker_id="9999",
        user_id="u",
        password="p",
        td_front="tcp://1.2.3.4:1",
        md_front="tcp://1.2.3.4:2",
    )
    return gw


class TestStateMachineIntegration:
    def test_gateway_has_state_machine(self, gateway):
        assert gateway.state_machine is not None
        assert gateway.state_machine.state == ConnectionState.IDLE

    def test_connect_transitions_to_connected(self, gateway):
        with patch.object(gateway._md_login_event, "wait", return_value=True):
            with patch.object(gateway._td_login_event, "wait", return_value=True):
                with patch.object(gateway, "_event_dispatcher"):
                    gateway.connect()
        assert gateway.state_machine.state == ConnectionState.CONNECTED

    def test_disconnect_transitions_to_disconnected(self, gateway):
        with patch.object(gateway._md_login_event, "wait", return_value=True):
            with patch.object(gateway._td_login_event, "wait", return_value=True):
                with patch.object(gateway, "_event_dispatcher"):
                    gateway.connect()
        gateway.disconnect()
        assert gateway.state_machine.state == ConnectionState.DISCONNECTED

    def test_state_event_published_on_connect(self, gateway):
        events = []
        with patch.object(gateway, "send_event", side_effect=lambda topic, payload: events.append((topic, payload))):
            with patch.object(gateway._md_login_event, "wait", return_value=True):
                with patch.object(gateway._td_login_event, "wait", return_value=True):
                    with patch.object(gateway, "_event_dispatcher"):
                        gateway.connect()
        state_events = [e for e in events if e[0] == "gateway.state"]
        assert len(state_events) >= 1
        payload = state_events[-1][1]
        assert payload["state"] == "CONNECTED"
        assert payload["venue"] == "openctp"


class TestErrorEventPublishing:
    def test_on_rsp_error_publishes_error_event(self, gateway):
        events = []
        with patch.object(gateway, "send_event", side_effect=lambda topic, payload: events.append((topic, payload))):
            spi = gateway._TdSpi(gateway)
            mock_rsp = MagicMock()
            mock_rsp.ErrorID = 3
            mock_rsp.ErrorMsg = b"not login\x00"
            spi.OnRspError(mock_rsp, 0, False)
        error_events = [e for e in events if e[0] == "gateway.error"]
        assert len(error_events) == 1
        payload = error_events[0][1]
        assert payload["error_id"] == 3
        assert payload["error_msg"] == "not login"


class TestPositionAccumulation:
    def test_position_accumulated_and_published(self, gateway):
        events = []
        with patch.object(gateway, "send_event", side_effect=lambda topic, payload: events.append((topic, payload))):
            spi = gateway._TdSpi(gateway)
            mock_pos = MagicMock()
            mock_pos.InstrumentID = b"rb2410\x00"
            mock_pos.PosiDirection = b"2\x00"
            mock_pos.Position = 5
            mock_pos.OpenCost = 35000.0
            spi.OnRspQryInvestorPosition(mock_pos, None, 0, True)
            # Drain the event queue to trigger publish_position_update
            event_type, payload = gateway._event_queue.get_nowait()
            assert event_type == "position_update"
            gateway.publish_position_update(payload)
        pos_events = [e for e in events if e[0] == "position.update"]
        assert len(pos_events) == 1
        payload = pos_events[0][1]
        assert payload["instrument_id"] == "rb2410.openctp.futures"

    def test_multiple_positions_accumulated(self, gateway):
        events = []
        with patch.object(gateway, "send_event", side_effect=lambda topic, payload: events.append((topic, payload))):
            spi = gateway._TdSpi(gateway)
            pos1 = MagicMock()
            pos1.InstrumentID = b"rb2410\x00"
            pos1.PosiDirection = b"2\x00"
            pos1.Position = 3
            pos1.OpenCost = 21000.0
            spi.OnRspQryInvestorPosition(pos1, None, 0, False)
            pos2 = MagicMock()
            pos2.InstrumentID = b"rb2410\x00"
            pos2.PosiDirection = b"2\x00"
            pos2.Position = 2
            pos2.OpenCost = 14000.0
            spi.OnRspQryInvestorPosition(pos2, None, 0, True)
            # Drain the event queue to trigger publish_position_update
            event_type, payload = gateway._event_queue.get_nowait()
            assert event_type == "position_update"
            gateway.publish_position_update(payload)
        pos_events = [e for e in events if e[0] == "position.update"]
        assert len(pos_events) == 1
        payload = pos_events[0][1]
        assert payload["instrument_id"] == "rb2410.openctp.futures"
        from decimal import Decimal
        assert Decimal(payload["quantity"]) == Decimal("5")
