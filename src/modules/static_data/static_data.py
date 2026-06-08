"""Static Data Module - TycheEngine module implementation."""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from src.modules.static_data.client import OpenCtpDataClient
from src.modules.static_data.config import StaticDataConfig
from src.modules.static_data.storage import StaticDataStorage
from src.tyche.module import TycheModule
from src.tyche.types import Endpoint

logger = logging.getLogger(__name__)


class StaticDataModule(TycheModule):
    """静态数据模块.

    功能:
    1. 定期从 OpenCTP DataCenter 拉取交易所、品种、合约、报价、交易时段数据
    2. 持久化到 data/static/ 目录下的 JSON 文件
    3. 通过 TycheEngine Job 接口提供查询服务:
       - handle_query_markets      -> 查询交易所信息
       - handle_query_products     -> 查询品种信息
       - handle_query_instruments  -> 查询合约信息
       - handle_query_prices       -> 查询报价信息
       - handle_query_times        -> 查询交易时段
       - handle_query_metadata     -> 查询数据元信息
       - handle_refresh_data       -> 手动触发数据刷新
    """

    def __init__(self, config: StaticDataConfig):
        engine_endpoint = Endpoint(config.engine_host, config.engine_port)
        # Heartbeat receive endpoint: engine heartbeat PUB port + 1 = registration port + 5
        heartbeat_receive = Endpoint(
            config.engine_host, config.engine_port + 5
        )
        super().__init__(
            engine_endpoint=engine_endpoint,
            family_name="static_data",
            heartbeat_receive_endpoint=heartbeat_receive,
        )
        self.config = config
        self.client = OpenCtpDataClient(config)
        self.storage = StaticDataStorage(config.data_dir)

        # In-memory cache for fast queries
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_lock = threading.RLock()
        self._last_refresh: Optional[float] = None

        # Background refresh thread
        self._refresh_thread: Optional[threading.Thread] = None
        self._refresh_stop_event = threading.Event()

    def start(self) -> None:
        """Start module: register with engine, load cached data, start refresh loop."""
        super().start()
        self._load_from_disk()
        self._start_refresh_loop()
        logger.info("[static_data] Module started, data_dir=%s", self.config.data_dir)

    def stop(self) -> None:
        """Stop module gracefully."""
        self._refresh_stop_event.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=2.0)
        self.client.close()
        super().stop()
        logger.info("[static_data] Module stopped")

    # ── Background Refresh ─────────────────────────────────────────

    def _start_refresh_loop(self) -> None:
        """Start the periodic background refresh thread."""
        self._refresh_stop_event.clear()
        self._refresh_thread = threading.Thread(
            target=self._refresh_worker,
            name="static_data_refresh",
            daemon=True,
        )
        self._refresh_thread.start()

    def _refresh_worker(self) -> None:
        """Worker that periodically fetches and stores static data."""
        # Initial refresh on startup
        self._do_refresh()

        while not self._refresh_stop_event.is_set():
            # Wait for refresh_interval or until stop event
            if self._refresh_stop_event.wait(self.config.refresh_interval):
                break
            self._do_refresh()

    def _do_refresh(self) -> None:
        """Perform a single refresh: fetch all data and persist."""
        if self._refresh_stop_event.is_set():
            return
        try:
            logger.info("[static_data] Starting data refresh...")
            data = self.client.fetch_all()
            if self._refresh_stop_event.is_set():
                return
            self.storage.save_all(data)
            self._update_cache(data)
            self._last_refresh = time.time()
            logger.info("[static_data] Data refresh completed")
        except Exception as e:
            logger.error("[static_data] Data refresh failed: %s", e)

    # ── Cache Management ───────────────────────────────────────────

    def _load_from_disk(self) -> None:
        """Load all persisted data into memory cache."""
        all_data = self.storage.load_all()
        with self._cache_lock:
            for category in StaticDataStorage.CATEGORIES:
                record = all_data.get(category)
                if record:
                    self._cache[category] = record.get("data", [])
                else:
                    self._cache[category] = []
        logger.info("[static_data] Loaded %d categories from disk", len(self._cache))

    def _update_cache(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Update in-memory cache with fresh data."""
        with self._cache_lock:
            for category, items in data.items():
                self._cache[category] = items

    def _get_cached(self, category: str) -> List[Dict[str, Any]]:
        """Get cached data for a category."""
        with self._cache_lock:
            return list(self._cache.get(category, []))

    # ── Job Handlers (Query API) ───────────────────────────────────

    def handle_query_markets(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询交易所信息.

        Payload:
            - exchange_id: Optional[str]  按交易所ID过滤
            - area: Optional[str]         按地区过滤
        """
        data = self._get_cached("markets")
        filters = self._build_filters(payload, ["ExchangeID", "Area"])
        return {"markets": self._apply_filters(data, filters)}

    def handle_query_products(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询品种信息.

        Payload:
            - exchange_id: Optional[str]  按交易所ID过滤
            - product_id: Optional[str]   按品种ID过滤
            - product_class: Optional[str] 按商品类别过滤
        """
        data = self._get_cached("products")
        filters = self._build_filters(payload, ["ExchangeID", "ProductID", "ProductClass"])
        return {"products": self._apply_filters(data, filters)}

    def handle_query_instruments(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询合约信息.

        Payload:
            - exchange_id: Optional[str]      按交易所ID过滤
            - product_id: Optional[str]       按品种ID过滤
            - instrument_id: Optional[str]    按合约ID过滤
            - product_class: Optional[str]    按商品类别过滤
            - inst_life_phase: Optional[str]  按合约状态过滤
        """
        data = self._get_cached("instruments")
        filters = self._build_filters(
            payload,
            ["ExchangeID", "ProductID", "InstrumentID", "ProductClass", "InstLifePhase"],
        )
        return {"instruments": self._apply_filters(data, filters)}

    def handle_query_prices(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询报价信息.

        Payload:
            - exchange_id: Optional[str]    按交易所ID过滤
            - product_id: Optional[str]     按品种ID过滤
            - instrument_id: Optional[str]  按合约ID过滤
        """
        data = self._get_cached("prices")
        filters = self._build_filters(payload, ["ExchangeID", "ProductID", "InstrumentID"])
        return {"prices": self._apply_filters(data, filters)}

    def handle_query_times(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询交易时段.

        Payload:
            - exchange_id: Optional[str]  按交易所ID过滤
            - product_id: Optional[str]   按品种ID过滤
        """
        data = self._get_cached("times")
        filters = self._build_filters(payload, ["ExchangeID", "ProductID"])
        return {"times": self._apply_filters(data, filters)}

    def handle_query_metadata(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 查询数据元信息.

        Returns counts and last update times for all categories.
        """
        metadata = self.storage.get_metadata()
        return {
            "metadata": metadata,
            "last_refresh": self._last_refresh,
            "refresh_interval": self.config.refresh_interval,
        }

    def handle_refresh_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Job handler: 手动触发数据刷新.

        Returns immediately; refresh runs in background.
        """
        threading.Thread(
            target=self._do_refresh,
            name="static_data_manual_refresh",
            daemon=True,
        ).start()
        return {"status": "refresh_triggered", "last_refresh": self._last_refresh}

    # ── Filter Helpers ─────────────────────────────────────────────

    @staticmethod
    def _build_filters(
        payload: Dict[str, Any], field_names: List[str]
    ) -> Dict[str, Any]:
        """Build filter map from payload keys to CTP field names.

        Maps snake_case payload keys to PascalCase field names.
        """
        filters: Dict[str, Any] = {}
        key_map = {
            "exchange_id": "ExchangeID",
            "product_id": "ProductID",
            "instrument_id": "InstrumentID",
            "product_class": "ProductClass",
            "inst_life_phase": "InstLifePhase",
            "area": "Area",
        }
        for payload_key, field_name in key_map.items():
            if field_name in field_names and payload_key in payload:
                value = payload[payload_key]
                if value is not None and value != "":
                    filters[field_name] = value
        return filters

    @staticmethod
    def _apply_filters(
        data: List[Dict[str, Any]], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply field-value filters to data list."""
        if not filters:
            return data
        result = []
        for item in data:
            match = True
            for field, value in filters.items():
                item_value = item.get(field)
                if item_value is None:
                    match = False
                    break
                # Support list of values for OR matching
                if isinstance(value, list):
                    if item_value not in value:
                        match = False
                        break
                else:
                    if str(item_value) != str(value):
                        match = False
                        break
            if match:
                result.append(item)
        return result
