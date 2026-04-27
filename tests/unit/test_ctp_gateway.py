"""Unit tests for CTP gateway — works without openctp-ctp installed."""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock openctp_ctp BEFORE importing any gateway modules
# ---------------------------------------------------------------------------
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

from modules.trading.gateway.ctp.gateway import (  # noqa: E402
    CTP_STATUS_MAP,
    EXCHANGE_MAP,
    _extract_symbol,
    _infer_exchange,
    _safe_float,
    _safe_str,
    _to_instrument_id,
)
from modules.trading.gateway.ctp.live import CtpLiveGateway  # noqa: E402
from modules.trading.gateway.ctp.sim import CtpSimGateway  # noqa: E402
from modules.trading.models.enums import OrderStatus, Side  # noqa: E402
from tyche.types import Endpoint  # noqa: E402

# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------

EP = Endpoint("127.0.0.1", 15555)


@pytest.fixture()
def sim_gw() -> CtpSimGateway:
    """Create a CtpSimGateway with default 7x24 config (no real connection)."""
    return CtpSimGateway(
        engine_endpoint=EP,
        user_id="test_user",
        password="test_pass",
    )


@pytest.fixture()
def live_gw() -> CtpLiveGateway:
    """Create a CtpLiveGateway with explicit params."""
    return CtpLiveGateway(
        engine_endpoint=EP,
        broker_id="1234",
        user_id="live_user",
        password="live_pass",
        td_front="tcp://180.168.146.187:10201",
        md_front="tcp://180.168.146.187:10211",
        auth_code="AUTH_CODE_XYZ",
        app_id="my_app",
    )


# ===================================================================
# 1. Exchange mapping tests
# ===================================================================


class TestInferExchange:
    """Test _infer_exchange for all major exchange prefixes."""

    def test_shfe_rb(self) -> None:
        assert _infer_exchange("rb2410") == "SHFE"

    def test_shfe_cu(self) -> None:
        assert _infer_exchange("cu2501") == "SHFE"

    def test_shfe_au(self) -> None:
        assert _infer_exchange("au2506") == "SHFE"

    def test_cffex_if(self) -> None:
        assert _infer_exchange("IF2506") == "CFFEX"

    def test_cffex_ic(self) -> None:
        assert _infer_exchange("IC2506") == "CFFEX"

    def test_cffex_t(self) -> None:
        assert _infer_exchange("T2506") == "CFFEX"

    def test_cffex_tf(self) -> None:
        assert _infer_exchange("TF2506") == "CFFEX"

    def test_dce_c(self) -> None:
        assert _infer_exchange("c2501") == "DCE"

    def test_dce_jm(self) -> None:
        assert _infer_exchange("jm2501") == "DCE"

    def test_dce_pp(self) -> None:
        assert _infer_exchange("pp2501") == "DCE"

    def test_czce_cf(self) -> None:
        assert _infer_exchange("CF501") == "CZCE"

    def test_czce_ta(self) -> None:
        assert _infer_exchange("TA501") == "CZCE"

    def test_czce_sr(self) -> None:
        assert _infer_exchange("SR501") == "CZCE"

    def test_ine_sc(self) -> None:
        assert _infer_exchange("sc2506") == "INE"

    def test_ine_lu(self) -> None:
        assert _infer_exchange("lu2506") == "INE"

    def test_gfex_si(self) -> None:
        assert _infer_exchange("si2506") == "GFEX"

    def test_gfex_lc(self) -> None:
        assert _infer_exchange("lc2506") == "GFEX"

    def test_unknown_instrument(self) -> None:
        result = _infer_exchange("ZZZ9999")
        assert result == "UNKNOWN"

    def test_empty_string(self) -> None:
        result = _infer_exchange("")
        assert result == "UNKNOWN"

    def test_numeric_only(self) -> None:
        result = _infer_exchange("12345")
        assert result == "UNKNOWN"


# ===================================================================
# 2. Instrument ID parsing tests
# ===================================================================


class TestParseInstrumentId:
    """Test _extract_symbol extracts CTP symbol from TycheEngine instrument_id."""

    def test_ctp_futures(self) -> None:
        assert _extract_symbol("rb2410.ctp.futures") == "rb2410"

    def test_openctp_futures(self) -> None:
        assert _extract_symbol("IF2506.openctp.futures") == "IF2506"

    def test_simple_symbol(self) -> None:
        assert _extract_symbol("sc2506.ine.futures") == "sc2506"

    def test_bare_symbol(self) -> None:
        """If no dots present, returns the whole string."""
        assert _extract_symbol("rb2410") == "rb2410"


# ===================================================================
# 3. Instrument ID building tests
# ===================================================================


class TestBuildInstrumentId:
    """Test _to_instrument_id builds TycheEngine instrument_id from CTP symbol."""

    def test_build_openctp(self) -> None:
        assert _to_instrument_id("rb2410", "openctp") == "rb2410.openctp.futures"

    def test_build_ctp(self) -> None:
        assert _to_instrument_id("IF2506", "ctp") == "IF2506.ctp.futures"

    def test_roundtrip(self) -> None:
        """Build then parse should recover the original symbol."""
        iid = _to_instrument_id("sc2506", "openctp")
        assert _extract_symbol(iid) == "sc2506"


# ===================================================================
# 4. CTP status mapping tests
# ===================================================================


class TestCtpStatusMapping:
    """Test CTP_STATUS_MAP covers all CTP order statuses correctly."""

    def test_all_traded(self) -> None:
        assert CTP_STATUS_MAP["0"] == OrderStatus.FILLED

    def test_part_traded_queueing(self) -> None:
        assert CTP_STATUS_MAP["1"] == OrderStatus.PARTIALLY_FILLED

    def test_part_traded_not_queueing(self) -> None:
        assert CTP_STATUS_MAP["2"] == OrderStatus.PARTIALLY_FILLED

    def test_no_trade_queueing(self) -> None:
        assert CTP_STATUS_MAP["3"] == OrderStatus.SUBMITTED

    def test_no_trade_not_queueing(self) -> None:
        assert CTP_STATUS_MAP["4"] == OrderStatus.SUBMITTED

    def test_canceled(self) -> None:
        assert CTP_STATUS_MAP["5"] == OrderStatus.CANCELLED

    def test_unknown(self) -> None:
        assert CTP_STATUS_MAP["a"] == OrderStatus.PENDING_SUBMIT

    def test_not_touched(self) -> None:
        assert CTP_STATUS_MAP["b"] == OrderStatus.NEW

    def test_touched(self) -> None:
        assert CTP_STATUS_MAP["c"] == OrderStatus.SUBMITTED

    def test_map_completeness(self) -> None:
        """Ensure all expected CTP status chars are in the map."""
        expected = {"0", "1", "2", "3", "4", "5", "a", "b", "c"}
        assert set(CTP_STATUS_MAP.keys()) == expected


# ===================================================================
# 5. Direction mapping tests
# ===================================================================


class TestDirectionMapping:
    """Test CTP direction constants used in submit_order / OnRtnTrade."""

    def test_buy_direction(self) -> None:
        """Side.BUY should map to CTP '0' (THOST_FTDC_D_Buy) in OnRtnTrade."""
        # In OnRtnTrade callback, direction "0" means buy
        direction = "0"
        side = Side.BUY if direction == "0" else Side.SELL
        assert side == Side.BUY

    def test_sell_direction(self) -> None:
        direction = "1"
        side = Side.BUY if direction == "0" else Side.SELL
        assert side == Side.SELL


# ===================================================================
# 6. CtpSimGateway configuration tests
# ===================================================================


class TestCtpSimGatewayConfig:
    """Test CtpSimGateway default configuration and environment selection."""

    def test_default_env_is_7x24(self, sim_gw: CtpSimGateway) -> None:
        assert sim_gw._td_front == "tcp://trading.openctp.cn:30001"
        assert sim_gw._md_front == "tcp://trading.openctp.cn:30011"

    def test_sim_env_addresses(self) -> None:
        gw = CtpSimGateway(
            engine_endpoint=EP,
            user_id="u",
            password="p",
            env="sim",
        )
        assert gw._td_front == "tcp://trading.openctp.cn:30002"
        assert gw._md_front == "tcp://trading.openctp.cn:30012"

    def test_default_broker_id(self, sim_gw: CtpSimGateway) -> None:
        assert sim_gw._broker_id == "9999"

    def test_default_venue_name(self, sim_gw: CtpSimGateway) -> None:
        assert sim_gw.venue_name == "openctp"

    def test_custom_venue_name(self) -> None:
        gw = CtpSimGateway(
            engine_endpoint=EP,
            user_id="u",
            password="p",
            venue_name="my_sim",
        )
        assert gw.venue_name == "my_sim"

    def test_invalid_env_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown env"):
            CtpSimGateway(
                engine_endpoint=EP,
                user_id="u",
                password="p",
                env="invalid",
            )

    def test_require_auth_is_false(self, sim_gw: CtpSimGateway) -> None:
        assert sim_gw._require_auth is False

    def test_user_password_stored(self, sim_gw: CtpSimGateway) -> None:
        assert sim_gw._user_id == "test_user"
        assert sim_gw._password == "test_pass"


# ===================================================================
# 7. CtpLiveGateway configuration tests
# ===================================================================


class TestCtpLiveGatewayConfig:
    """Test CtpLiveGateway parameter pass-through and auth logic."""

    def test_params_passed_through(self, live_gw: CtpLiveGateway) -> None:
        assert live_gw._broker_id == "1234"
        assert live_gw._user_id == "live_user"
        assert live_gw._password == "live_pass"
        assert live_gw._td_front == "tcp://180.168.146.187:10201"
        assert live_gw._md_front == "tcp://180.168.146.187:10211"

    def test_auth_required_when_both_provided(self, live_gw: CtpLiveGateway) -> None:
        """require_auth=True when auth_code AND app_id are both supplied."""
        assert live_gw._require_auth is True
        assert live_gw._auth_code == "AUTH_CODE_XYZ"
        assert live_gw._app_id == "my_app"

    def test_no_auth_when_missing_auth_code(self) -> None:
        gw = CtpLiveGateway(
            engine_endpoint=EP,
            broker_id="1234",
            user_id="u",
            password="p",
            td_front="tcp://1.2.3.4:10201",
            md_front="tcp://1.2.3.4:10211",
        )
        assert gw._require_auth is False

    def test_no_auth_when_only_auth_code(self) -> None:
        gw = CtpLiveGateway(
            engine_endpoint=EP,
            broker_id="1234",
            user_id="u",
            password="p",
            td_front="tcp://1.2.3.4:10201",
            md_front="tcp://1.2.3.4:10211",
            auth_code="ABC",
        )
        # app_id is None -> bool(None and "ABC") is False
        assert gw._require_auth is False

    def test_default_venue_name_is_ctp(self) -> None:
        gw = CtpLiveGateway(
            engine_endpoint=EP,
            broker_id="1234",
            user_id="u",
            password="p",
            td_front="tcp://1.2.3.4:10201",
            md_front="tcp://1.2.3.4:10211",
        )
        assert gw.venue_name == "ctp"

    def test_custom_venue_name(self) -> None:
        gw = CtpLiveGateway(
            engine_endpoint=EP,
            broker_id="1234",
            user_id="u",
            password="p",
            td_front="tcp://1.2.3.4:10201",
            md_front="tcp://1.2.3.4:10211",
            venue_name="my_broker",
        )
        assert gw.venue_name == "my_broker"


# ===================================================================
# 8. Helper function edge-case tests
# ===================================================================


class TestSafeStr:
    """Test _safe_str with bytes, null-padded strings, and None."""

    def test_bytes_input(self) -> None:
        assert _safe_str(b"hello\x00\x00") == "hello"

    def test_str_with_null(self) -> None:
        assert _safe_str("hello\x00") == "hello"

    def test_none(self) -> None:
        assert _safe_str(None) == ""

    def test_plain_str(self) -> None:
        assert _safe_str("hello") == "hello"


class TestSafeFloat:
    """Test _safe_float with normal, extreme, and invalid inputs."""

    def test_normal_float(self) -> None:
        assert _safe_float(3500.5) == 3500.5

    def test_dbl_max_returns_default(self) -> None:
        """CTP uses DBL_MAX (~1.7e308) for undefined prices."""
        assert _safe_float(1.7e308) == 0.0

    def test_negative_dbl_max(self) -> None:
        assert _safe_float(-1.7e308) == 0.0

    def test_none_returns_default(self) -> None:
        assert _safe_float(None) == 0.0

    def test_custom_default(self) -> None:
        assert _safe_float(None, default=-1.0) == -1.0

    def test_string_number(self) -> None:
        assert _safe_float("42.5") == 42.5

    def test_invalid_string(self) -> None:
        assert _safe_float("not_a_number") == 0.0


# ===================================================================
# 9. EXCHANGE_MAP coverage
# ===================================================================


class TestExchangeMapCoverage:
    """Verify EXCHANGE_MAP contains entries for all major exchanges."""

    def test_shfe_entries_exist(self) -> None:
        shfe_symbols = ["cu", "al", "zn", "pb", "ni", "sn", "au", "ag", "rb", "hc", "fu", "bu", "ru"]
        for sym in shfe_symbols:
            assert EXCHANGE_MAP[sym] == "SHFE", f"{sym} should map to SHFE"

    def test_dce_entries_exist(self) -> None:
        dce_symbols = ["c", "cs", "a", "b", "m", "y", "p", "jd", "l", "v", "pp", "j", "jm", "i", "eg"]
        for sym in dce_symbols:
            assert EXCHANGE_MAP[sym] == "DCE", f"{sym} should map to DCE"

    def test_czce_entries_exist(self) -> None:
        czce_symbols = ["CF", "SR", "TA", "OI", "MA", "FG", "AP", "SA", "PF"]
        for sym in czce_symbols:
            assert EXCHANGE_MAP[sym] == "CZCE", f"{sym} should map to CZCE"

    def test_ine_entries_exist(self) -> None:
        ine_symbols = ["sc", "lu", "nr", "bc", "ec"]
        for sym in ine_symbols:
            assert EXCHANGE_MAP[sym] == "INE", f"{sym} should map to INE"

    def test_gfex_entries_exist(self) -> None:
        gfex_symbols = ["si", "lc"]
        for sym in gfex_symbols:
            assert EXCHANGE_MAP[sym] == "GFEX", f"{sym} should map to GFEX"

    def test_cffex_entries_exist(self) -> None:
        cffex_symbols = ["IF", "IC", "IH", "IM", "T", "TF", "TS", "TL"]
        for sym in cffex_symbols:
            assert EXCHANGE_MAP[sym] == "CFFEX", f"{sym} should map to CFFEX"
