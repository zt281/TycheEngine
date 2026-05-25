"""Additional tests for src.modules.static_data.static_data to reach 85%+ coverage."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.modules.static_data.static_data import StaticDataModule
from src.modules.static_data.config import StaticDataConfig
from src.modules.static_data.storage import StaticDataStorage
from src.tyche.types import Endpoint


@pytest.fixture
def config(tmp_path):
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


class TestStaticDataModuleLifecycle:
    @patch("src.modules.static_data.static_data.StaticDataModule._load_from_disk")
    @patch("src.modules.static_data.static_data.StaticDataModule._start_refresh_loop")
    @patch("src.tyche.module.TycheModule.start")
    def test_start_calls_super_and_initializes(self, mock_super_start, mock_refresh, mock_load, config):
        module = StaticDataModule(config)
        module.start()
        mock_super_start.assert_called_once()
        mock_load.assert_called_once()
        mock_refresh.assert_called_once()

    @patch("src.tyche.module.TycheModule.stop")
    def test_stop_gracefully(self, mock_super_stop, config):
        module = StaticDataModule(config)
        module._refresh_thread = MagicMock()
        module._refresh_thread.join = MagicMock()
        module.client.close = MagicMock()
        module.stop()
        assert module._refresh_stop_event.is_set()
        module._refresh_thread.join.assert_called_once_with(timeout=2.0)
        module.client.close.assert_called_once()
        mock_super_stop.assert_called_once()

    @patch("src.tyche.module.TycheModule.stop")
    def test_stop_without_refresh_thread(self, mock_super_stop, config):
        module = StaticDataModule(config)
        module.client.close = MagicMock()
        module.stop()
        assert module._refresh_stop_event.is_set()
        mock_super_stop.assert_called_once()


class TestRefreshLoop:
    @patch("src.modules.static_data.static_data.StaticDataModule._do_refresh")
    def test_refresh_worker_runs_initial_refresh(self, mock_do_refresh, config):
        module = StaticDataModule(config)
        module._refresh_stop_event.set()  # Stop immediately after first iteration
        module._refresh_worker()
        mock_do_refresh.assert_called_once()

    @patch("src.modules.static_data.static_data.StaticDataModule._do_refresh")
    def test_refresh_worker_stops_on_event(self, mock_do_refresh, config):
        module = StaticDataModule(config)
        module._refresh_stop_event.set()
        module._refresh_worker()
        assert mock_do_refresh.call_count == 1  # Initial refresh still runs

    @patch("src.modules.static_data.static_data.OpenCtpDataClient.fetch_all")
    def test_do_refresh_stop_event_check_before_fetch(self, mock_fetch, config):
        module = StaticDataModule(config)
        module._refresh_stop_event.set()
        module._do_refresh()
        mock_fetch.assert_not_called()

    @patch("src.modules.static_data.static_data.OpenCtpDataClient.fetch_all")
    def test_do_refresh_stop_event_check_after_fetch(self, mock_fetch, config):
        module = StaticDataModule(config)
        mock_fetch.return_value = {"markets": []}
        module._refresh_stop_event.set()
        module._do_refresh()
        # fetch_all is called but stop event prevents storage
        mock_fetch.assert_called_once()
        assert module._last_refresh is None  # Not updated because stop event set

    def test_start_refresh_loop(self, config):
        module = StaticDataModule(config)
        module._refresh_stop_event.set()  # Pre-set to prevent actual worker loop
        module._start_refresh_loop()
        assert module._refresh_thread is not None
        assert module._refresh_thread.daemon is True
        assert module._refresh_thread.name == "static_data_refresh"
        module._refresh_stop_event.set()  # Clean stop
        if module._refresh_thread.is_alive():
            module._refresh_thread.join(timeout=1.0)


class TestApplyFiltersEdgeCases:
    def test_apply_filters_with_list_values(self):
        data = [
            {"ExchangeID": "SHFE", "ProductID": "au"},
            {"ExchangeID": "SHFE", "ProductID": "rb"},
            {"ExchangeID": "CFFEX", "ProductID": "IF"},
        ]
        # Match any of ["au", "rb"]
        result = StaticDataModule._apply_filters(data, {"ProductID": ["au", "rb"]})
        assert len(result) == 2
        assert result[0]["ProductID"] == "au"
        assert result[1]["ProductID"] == "rb"

    def test_apply_filters_list_value_no_match(self):
        data = [
            {"ExchangeID": "SHFE", "ProductID": "au"},
        ]
        result = StaticDataModule._apply_filters(data, {"ProductID": ["rb", "cu"]})
        assert len(result) == 0

    def test_apply_filters_none_item_value(self):
        """Item with None field value should not match."""
        data = [
            {"ExchangeID": "SHFE", "ProductID": None},
            {"ExchangeID": "SHFE", "ProductID": "au"},
        ]
        result = StaticDataModule._apply_filters(data, {"ProductID": "au"})
        assert len(result) == 1
        assert result[0]["ProductID"] == "au"


class TestHandleRefreshData:
    def test_handle_refresh_data_returns_triggered(self, config):
        module = StaticDataModule(config)
        result = module.handle_refresh_data({})
        assert result["status"] == "refresh_triggered"
        assert result["last_refresh"] is None
