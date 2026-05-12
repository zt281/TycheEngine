"""Tests for enhanced CTP gateway features: state machine, errors, positions."""
import sys
from decimal import Decimal
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

# Assign real string values to CTP constants used in submit_order
_mock_tdapi.THOST_FTDC_OPT_LimitPrice = "2"
_mock_tdapi.THOST_FTDC_OPT_AnyPrice = "1"
_mock_tdapi.THOST_FTDC_OPT_BestPrice = "3"
_mock_tdapi.THOST_FTDC_D_Buy = "0"
_mock_tdapi.THOST_FTDC_D_Sell = "1"
_mock_tdapi.THOST_FTDC_OF_Open = "0"
_mock_tdapi.THOST_FTDC_OF_Close = "1"
_mock_tdapi.THOST_FTDC_OF_CloseToday = "3"
_mock_tdapi.THOST_FTDC_OF_CloseYesterday = "4"
_mock_tdapi.THOST_FTDC_TC_IOC = "1"
_mock_tdapi.THOST_FTDC_TC_GFS = "2"
_mock_tdapi.THOST_FTDC_TC_GFD = "3"
_mock_tdapi.THOST_FTDC_VC_AV = "1"
_mock_tdapi.THOST_FTDC_VC_CV = "2"
_mock_tdapi.THOST_FTDC_CC_Immediately = "1"
_mock_tdapi.THOST_FTDC_CC_Touch = "2"
_mock_tdapi.THOST_FTDC_HF_Speculation = "1"
_mock_tdapi.THOST_FTDC_FCC_NotForceClose = "0"
_mock_tdapi.CThostFtdcInputOrderField = MagicMock
_mock_tdapi.CThostFtdcQryTradingAccountField = MagicMock
_mock_tdapi.CThostFtdcQryInvestorPositionField = MagicMock
_mock_tdapi.CThostFtdcInputOrderActionField = MagicMock
_mock_tdapi.CThostFtdcReqUserLoginField = MagicMock
_mock_tdapi.CThostFtdcReqAuthenticateField = MagicMock
_mock_tdapi.THOST_TERT_QUICK = 1

import pytest  # noqa: E402

# Ensure gateway module uses our mock tdapi (prevents cross-module cache issues)
import modules.trading.gateway.ctp.gateway as _ctp_gw_mod  # noqa: E402
from modules.trading.gateway.ctp.gateway import CtpGateway  # noqa: E402
from modules.trading.gateway.ctp.state_machine import (  # noqa: E402
    ConnectionState,
    ConnectionStateMachine,
)
from tyche.types import Endpoint  # noqa: E402

_ctp_gw_mod.tdapi = _mock_tdapi

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


class TestAutoReconnect:
    def test_front_disconnected_triggers_reconnecting(self, gateway):
        with patch.object(gateway, "_create_and_connect_apis"):
            with patch.object(gateway._md_login_event, "wait", return_value=True):
                with patch.object(gateway._td_login_event, "wait", return_value=True):
                    with patch.object(gateway, "_event_dispatcher"):
                        gateway.connect()
        assert gateway.state_machine.state == ConnectionState.CONNECTED
        spi = gateway._MdSpi(gateway)
        spi.OnFrontDisconnected(0)
        assert gateway.state_machine.state == ConnectionState.RECONNECTING

    def test_reconnect_backoff_calculated(self, gateway):
        with patch.object(gateway, "_create_and_connect_apis"):
            with patch.object(gateway._md_login_event, "wait", return_value=True):
                with patch.object(gateway._td_login_event, "wait", return_value=True):
                    with patch.object(gateway, "_event_dispatcher"):
                        gateway.connect()
        spi = gateway._MdSpi(gateway)
        spi.OnFrontDisconnected(0)
        delay = gateway.state_machine.next_backoff_ms()
        assert delay >= 1000
        assert delay <= 30000

    def test_max_retries_leads_to_disconnected(self, gateway):
        from modules.trading.gateway.ctp.state_machine import ReconnectConfig
        gateway.state_machine = ConnectionStateMachine(
            venue="openctp",
            reconnect_config=ReconnectConfig(max_retries=1),
        )
        with patch.object(gateway, "_create_and_connect_apis"):
            with patch.object(gateway._md_login_event, "wait", return_value=True):
                with patch.object(gateway._td_login_event, "wait", return_value=True):
                    with patch.object(gateway, "_event_dispatcher"):
                        gateway.connect()
        spi = gateway._MdSpi(gateway)
        spi.OnFrontDisconnected(0)
        assert gateway.state_machine.state == ConnectionState.RECONNECTING
        gateway.state_machine.transition(ConnectionState.CONNECTING)
        gateway.state_machine.transition(ConnectionState.CONNECTED)
        spi.OnFrontDisconnected(0)
        assert gateway.state_machine.max_retries_exceeded() is True


class TestOffsetMapping:
    """Test CTP offset flag mapping."""

    def test_offset_map_values(self):
        from modules.trading.gateway.ctp.gateway import OFFSET_MAP
        from modules.trading.models.enums import Offset
        assert OFFSET_MAP[Offset.OPEN] == "0"
        assert OFFSET_MAP[Offset.CLOSE] == "1"
        assert OFFSET_MAP[Offset.CLOSE_TODAY] == "3"
        assert OFFSET_MAP[Offset.CLOSE_YESTERDAY] == "4"


class TestSubmitOrderMapping:
    """Test submit_order correctly maps Order fields to CTP InputOrderField."""

    def test_limit_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        order = MagicMock()
        order.instrument_id = "rb2410.openctp.futures"
        order.side.name = "BUY"
        order.offset = MagicMock()
        order.offset.name = "OPEN"
        order.order_type.name = "LIMIT"
        order.order_type = MagicMock()
        order.order_type = gateway._TdSpi.__class__  # dummy
        order.quantity = Decimal("10")
        order.price = Decimal("3500")
        order.stop_price = None
        order.time_in_force.name = "GTC"
        order.order_id = "oid_123"
        order.time_in_force = MagicMock()

        # Build a real-ish order object
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            price=Decimal("3500"),
            time_in_force=TimeInForce.GTC,
            offset=Offset.OPEN,
            order_id="oid_123",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.OrderPriceType == "2"  # THOST_FTDC_OPT_LimitPrice
        assert req.LimitPrice == 3500.0
        assert req.ContingentCondition == "1"  # Immediately
        assert req.CombOffsetFlag == "0"  # Open
        assert req.TimeCondition == "3"  # GFD

    def test_market_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal("5"),
            time_in_force=TimeInForce.DAY,
            offset=Offset.CLOSE,
            order_id="oid_456",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.OrderPriceType == "1"  # AnyPrice
        assert req.LimitPrice == 0.0
        assert req.CombOffsetFlag == "1"  # Close
        assert req.TimeCondition == "3"  # GFD

    def test_stop_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.BUY,
            order_type=OrderType.STOP,
            quantity=Decimal("2"),
            stop_price=Decimal("3600"),
            time_in_force=TimeInForce.GTC,
            offset=Offset.OPEN,
            order_id="oid_789",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.OrderPriceType == "1"  # AnyPrice
        assert req.LimitPrice == 0.0
        assert req.StopPrice == 3600.0
        assert req.ContingentCondition == "2"  # Touch
        assert req.CombOffsetFlag == "0"

    def test_stop_limit_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.SELL,
            order_type=OrderType.STOP_LIMIT,
            quantity=Decimal("3"),
            price=Decimal("3550"),
            stop_price=Decimal("3540"),
            time_in_force=TimeInForce.IOC,
            offset=Offset.CLOSE_TODAY,
            order_id="oid_abc",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.OrderPriceType == "2"  # LimitPrice
        assert req.LimitPrice == 3550.0
        assert req.StopPrice == 3540.0
        assert req.ContingentCondition == "2"  # Touch
        assert req.CombOffsetFlag == "3"  # CloseToday
        assert req.TimeCondition == "1"  # IOC
        assert req.VolumeCondition == "1"  # AV

    def test_fok_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("3500"),
            time_in_force=TimeInForce.FOK,
            offset=Offset.CLOSE_YESTERDAY,
            order_id="oid_def",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.TimeCondition == "1"  # IOC
        assert req.VolumeCondition == "2"  # CV
        assert req.CombOffsetFlag == "4"  # CloseYesterday

    def test_gtd_order_mapping(self, gateway):
        gateway._td_api = MagicMock()
        from modules.trading.models.enums import Offset, OrderType, Side, TimeInForce
        from modules.trading.models.order import Order
        order = Order(
            instrument_id="rb2410.openctp.futures",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            price=Decimal("3500"),
            time_in_force=TimeInForce.GTD,
            offset=Offset.OPEN,
            order_id="oid_ghi",
        )
        gateway.submit_order(order)
        req = gateway._td_api.ReqOrderInsert.call_args[0][0]
        assert req.TimeCondition == "2"  # GFS (closest to GTD)
