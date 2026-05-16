"""Tests for the Static Data module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from modules.static_data.client import OpenCtpDataClient
from modules.static_data.config import StaticDataConfig
from modules.static_data.storage import StaticDataStorage
from modules.static_data.static_data import StaticDataModule


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def config(tmp_path):
    """Provide a test configuration pointing to temp directories."""
    return StaticDataConfig(
        base_url="http://test.openctp.cn",
        refresh_interval=3600,
        data_dir=str(tmp_path / "static"),
        engine_host="127.0.0.1",
        engine_port=20550,
        areas=["China"],
        types=["futures"],
        markets=["SHFE"],
        products=["au"],
        retry_count=1,
        retry_delay=0,
    )


@pytest.fixture
def sample_markets():
    return [
        {"ExchangeID": "SHFE", "ExchangeName": "上海期货交易所", "TimeZone": 8, "ShortName": "上期所", "Area": "China"},
        {"ExchangeID": "CFFEX", "ExchangeName": "中国金融期货交易所", "TimeZone": 8, "ShortName": "中金所", "Area": "China"},
    ]


@pytest.fixture
def sample_products():
    return [
        {"ExchangeID": "SHFE", "ProductID": "au", "ProductName": "黄金", "ProductClass": "1"},
        {"ExchangeID": "SHFE", "ProductID": "rb", "ProductName": "螺纹钢", "ProductClass": "1"},
    ]


@pytest.fixture
def sample_instruments():
    return [
        {
            "ExchangeID": "SHFE",
            "InstrumentID": "au2506",
            "InstrumentName": "黄金2506",
            "ProductClass": "1",
            "ProductID": "au",
            "VolumeMultiple": 1000,
            "PriceTick": 0.02,
            "InstLifePhase": "1",
        },
        {
            "ExchangeID": "SHFE",
            "InstrumentID": "rb2506",
            "InstrumentName": "螺纹钢2506",
            "ProductClass": "1",
            "ProductID": "rb",
            "VolumeMultiple": 10,
            "PriceTick": 1,
            "InstLifePhase": "1",
        },
    ]


@pytest.fixture
def sample_prices():
    return [
        {
            "ExchangeID": "SHFE",
            "InstrumentID": "au2506",
            "InstrumentName": "au2506",
            "ProductID": "au",
            "ProductClass": "1",
            "LastPrice": 550.0,
            "Volume": 100,
        },
    ]


@pytest.fixture
def sample_times():
    return [
        {"ExchangeID": "SHFE", "ProductID": "au", "SegmentNo": 1, "TimeBegin": "21:00:00", "TimeEnd": "02:30:00", "ProductClass": "1", "Area": "China"},
    ]


@pytest.fixture
def mock_api_response(sample_markets, sample_products, sample_instruments, sample_prices, sample_times):
    """Return a dict of mock API responses per endpoint."""
    return {
        "markets": {"rsp_code": 0, "rsp_message": "succeed", "data": sample_markets},
        "products": {"rsp_code": 0, "rsp_message": "succeed", "data": sample_products},
        "instruments": {"rsp_code": 0, "rsp_message": "succeed", "data": sample_instruments},
        "prices": {"rsp_code": 0, "rsp_message": "succeed", "data": sample_prices},
        "times": {"rsp_code": 0, "rsp_message": "succeed", "data": sample_times},
    }


# ── Storage Tests ────────────────────────────────────────────────

class TestStaticDataStorage:
    def test_save_and_load(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        data = [{"ExchangeID": "SHFE", "ExchangeName": "上期所"}]
        storage.save("markets", data)

        loaded = storage.load("markets")
        assert loaded is not None
        assert loaded["count"] == 1
        assert loaded["data"] == data
        assert "updated_at" in loaded

    def test_load_missing_returns_none(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        assert storage.load("markets") is None

    def test_load_all(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        storage.save("markets", [{"id": 1}])
        storage.save("products", [{"id": 2}])

        all_data = storage.load_all()
        assert all_data["markets"]["count"] == 1
        assert all_data["products"]["count"] == 1
        assert all_data["instruments"] is None

    def test_save_all(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        data = {
            "markets": [{"id": 1}],
            "products": [{"id": 2}],
            "instruments": [{"id": 3}],
            "prices": [{"id": 4}],
            "times": [{"id": 5}],
        }
        storage.save_all(data)

        for cat in StaticDataStorage.CATEGORIES:
            loaded = storage.load(cat)
            assert loaded is not None
            assert loaded["count"] == 1

    def test_get_metadata(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        storage.save("markets", [{"id": 1}])
        storage.save("products", [{"id": 2}])

        meta = storage.get_metadata()
        assert meta["markets"]["count"] == 1
        assert meta["products"]["count"] == 1
        assert meta["instruments"]["count"] == 0
        assert meta["markets"]["updated_at"] is not None

    def test_invalid_category_raises(self, tmp_path):
        storage = StaticDataStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.save("invalid", [])
        with pytest.raises(ValueError):
            storage.load("invalid")


# ── Client Tests ─────────────────────────────────────────────────

class TestOpenCtpDataClient:
    def test_build_url_no_params(self, config):
        client = OpenCtpDataClient(config)
        url = client._build_url("markets")
        assert url == "http://test.openctp.cn/markets"

    def test_build_url_with_params(self, config):
        client = OpenCtpDataClient(config)
        url = client._build_url("products", {"types": "futures", "areas": "China"})
        assert "products?" in url
        assert "types=futures" in url
        assert "areas=China" in url

    def test_build_url_skips_empty_params(self, config):
        client = OpenCtpDataClient(config)
        url = client._build_url("products", {"types": "futures", "areas": None, "markets": []})
        assert "areas" not in url
        assert "markets" not in url
        assert "types=futures" in url

    @patch("modules.static_data.client.requests.Session.request")
    def test_get_markets_success(self, mock_request, config, sample_markets):
        mock_response = MagicMock()
        mock_response.json.return_value = {"rsp_code": 0, "rsp_message": "succeed", "data": sample_markets}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        client = OpenCtpDataClient(config)
        result = client.get_markets()
        assert result == sample_markets
        mock_request.assert_called_once()

    @patch("modules.static_data.client.requests.Session.request")
    def test_api_error_raises(self, mock_request, config):
        mock_response = MagicMock()
        mock_response.json.return_value = {"rsp_code": 1, "rsp_message": "error"}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        client = OpenCtpDataClient(config)
        with pytest.raises(RuntimeError, match="API error"):
            client.get_markets()

    @patch("modules.static_data.client.requests.Session.request")
    def test_retry_then_fail(self, mock_request, config):
        mock_request.side_effect = Exception("Network error")

        client = OpenCtpDataClient(config)
        with pytest.raises(RuntimeError, match="Request failed after"):
            client.get_markets()
        assert mock_request.call_count == config.retry_count

    @patch("modules.static_data.client.requests.Session.request")
    def test_fetch_all(self, mock_request, config, mock_api_response):
        def side_effect(method, url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            for key, value in mock_api_response.items():
                if f"/{key}" in url or url.endswith(key):
                    mock_resp.json.return_value = value
                    return mock_resp
            mock_resp.json.return_value = {"rsp_code": 0, "rsp_message": "succeed", "data": []}
            return mock_resp

        mock_request.side_effect = side_effect
        client = OpenCtpDataClient(config)
        result = client.fetch_all()

        assert "markets" in result
        assert "products" in result
        assert "instruments" in result
        assert "prices" in result
        assert "times" in result
        assert len(result["markets"]) == 2


# ── Module Tests ─────────────────────────────────────────────────

class TestStaticDataModule:
    def test_filter_helpers(self):
        data = [
            {"ExchangeID": "SHFE", "ProductID": "au", "ProductClass": "1"},
            {"ExchangeID": "SHFE", "ProductID": "rb", "ProductClass": "1"},
            {"ExchangeID": "CFFEX", "ProductID": "IF", "ProductClass": "1"},
        ]

        # No filters
        result = StaticDataModule._apply_filters(data, {})
        assert len(result) == 3

        # Single filter
        result = StaticDataModule._apply_filters(data, {"ExchangeID": "SHFE"})
        assert len(result) == 2

        # Multiple filters
        result = StaticDataModule._apply_filters(data, {"ExchangeID": "SHFE", "ProductID": "au"})
        assert len(result) == 1

        # No match
        result = StaticDataModule._apply_filters(data, {"ExchangeID": "DCE"})
        assert len(result) == 0

    def test_build_filters(self):
        payload = {"exchange_id": "SHFE", "product_id": "au", "unknown": "x"}
        filters = StaticDataModule._build_filters(payload, ["ExchangeID", "ProductID"])
        assert filters == {"ExchangeID": "SHFE", "ProductID": "au"}

    def test_build_filters_empty_value_ignored(self):
        payload = {"exchange_id": "", "product_id": "au"}
        filters = StaticDataModule._build_filters(payload, ["ExchangeID", "ProductID"])
        assert filters == {"ProductID": "au"}

    def test_query_handlers(self, config, sample_markets, sample_products, sample_instruments, sample_prices, sample_times):
        module = StaticDataModule(config)
        # Pre-populate cache
        module._cache = {
            "markets": sample_markets,
            "products": sample_products,
            "instruments": sample_instruments,
            "prices": sample_prices,
            "times": sample_times,
        }

        # Query all markets
        result = module.handle_query_markets({})
        assert len(result["markets"]) == 2

        # Filter by exchange
        result = module.handle_query_markets({"exchange_id": "SHFE"})
        assert len(result["markets"]) == 1
        assert result["markets"][0]["ExchangeID"] == "SHFE"

        # Query products
        result = module.handle_query_products({})
        assert len(result["products"]) == 2

        # Query instruments
        result = module.handle_query_instruments({})
        assert len(result["instruments"]) == 2

        # Filter instruments by product
        result = module.handle_query_instruments({"product_id": "au"})
        assert len(result["instruments"]) == 1
        assert result["instruments"][0]["InstrumentID"] == "au2506"

        # Query prices
        result = module.handle_query_prices({})
        assert len(result["prices"]) == 1

        # Query times
        result = module.handle_query_times({})
        assert len(result["times"]) == 1

        # Query metadata
        result = module.handle_query_metadata({})
        assert "metadata" in result
        assert result["last_refresh"] is None
        assert result["refresh_interval"] == config.refresh_interval

        # Refresh trigger
        result = module.handle_refresh_data({})
        assert result["status"] == "refresh_triggered"

    def test_load_from_disk(self, config, tmp_path):
        storage = StaticDataStorage(config.data_dir)
        storage.save("markets", [{"ExchangeID": "SHFE"}])
        storage.save("products", [{"ProductID": "au"}])

        module = StaticDataModule(config)
        module._load_from_disk()

        assert module._cache["markets"] == [{"ExchangeID": "SHFE"}]
        assert module._cache["products"] == [{"ProductID": "au"}]
        assert module._cache["instruments"] == []

    @patch("modules.static_data.static_data.OpenCtpDataClient.fetch_all")
    def test_do_refresh(self, mock_fetch, config, mock_api_response):
        mock_fetch.return_value = {
            k: v["data"] for k, v in mock_api_response.items()
        }
        module = StaticDataModule(config)
        module._do_refresh()

        assert module._last_refresh is not None
        assert len(module._cache["markets"]) == 2
        # Verify files were written
        storage = StaticDataStorage(config.data_dir)
        loaded = storage.load("markets")
        assert loaded is not None
        assert loaded["count"] == 2

    @patch("modules.static_data.static_data.OpenCtpDataClient.fetch_all")
    def test_do_refresh_failure_handled(self, mock_fetch, config):
        mock_fetch.side_effect = RuntimeError("API down")
        module = StaticDataModule(config)
        # Should not raise
        module._do_refresh()
        assert module._last_refresh is None
