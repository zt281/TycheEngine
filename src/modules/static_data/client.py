"""OpenCTP DataCenter REST API client."""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import requests

from .config import StaticDataConfig

logger = logging.getLogger(__name__)


class OpenCtpDataClient:
    """Client for OpenCTP DataCenter RESTful API.

    Endpoints:
        - /markets   -> 交易所信息
        - /products  -> 品种信息
        - /instruments -> 合约信息
        - /prices    -> 报价信息
        - /times     -> 交易时段
    """

    def __init__(self, config: StaticDataConfig):
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "TycheEngine-StaticData/1.0",
        })

    def _build_url(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Build full URL with query parameters."""
        base = urljoin(self.config.base_url, endpoint)
        if params:
            filtered = {k: v for k, v in params.items() if v is not None and v != []}
            if filtered:
                return f"{base}?{urlencode(filtered, doseq=False)}"
        return base

    def _request(self, method: str, url: str) -> Dict[str, Any]:
        """Execute HTTP request with retry logic."""
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.config.retry_count + 1):
            try:
                logger.debug("[%s] Requesting %s (attempt %d/%d)",
                             self.__class__.__name__, url, attempt, self.config.retry_count)
                response = self._session.request(
                    method,
                    url,
                    timeout=self.config.request_timeout,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("rsp_code") != 0:
                    raise RuntimeError(
                        f"API error: {data.get('rsp_message', 'unknown')} (code={data.get('rsp_code')})"
                    )
                return data

            except (requests.RequestException, json.JSONDecodeError) as e:
                last_exception = e
                logger.warning(
                    "[%s] Request failed (attempt %d/%d): %s",
                    self.__class__.__name__, attempt, self.config.retry_count, e,
                )
                if attempt < self.config.retry_count:
                    time.sleep(self.config.retry_delay)

        raise RuntimeError(
            f"Request failed after {self.config.retry_count} attempts: {last_exception}"
        )

    def _build_filter_params(self) -> Dict[str, Any]:
        """Build common filter parameters from config."""
        return {
            "types": ",".join(self.config.types) if self.config.types else None,
            "areas": ",".join(self.config.areas) if self.config.areas else None,
            "markets": ",".join(self.config.markets) if self.config.markets else None,
            "products": ",".join(self.config.products) if self.config.products else None,
        }

    def get_markets(self) -> List[Dict[str, Any]]:
        """Fetch exchange/market information."""
        params: Dict[str, Any] = {}
        if self.config.areas:
            params["areas"] = ",".join(self.config.areas)
        url = self._build_url("markets", params)
        response = self._request("GET", url)
        return response.get("data", [])

    def get_products(self) -> List[Dict[str, Any]]:
        """Fetch product information."""
        params = self._build_filter_params()
        url = self._build_url("products", params)
        response = self._request("GET", url)
        return response.get("data", [])

    def get_instruments(self) -> List[Dict[str, Any]]:
        """Fetch instrument/contract information."""
        params = self._build_filter_params()
        if self.config.instruments:
            params["instruments"] = ",".join(self.config.instruments)
        url = self._build_url("instruments", params)
        response = self._request("GET", url)
        return response.get("data", [])

    def get_prices(self) -> List[Dict[str, Any]]:
        """Fetch price quotation information."""
        params = self._build_filter_params()
        if self.config.instruments:
            params["instruments"] = ",".join(self.config.instruments)
        url = self._build_url("prices", params)
        response = self._request("GET", url)
        return response.get("data", [])

    def get_times(self) -> List[Dict[str, Any]]:
        """Fetch trading session/time information."""
        params = self._build_filter_params()
        url = self._build_url("times", params)
        response = self._request("GET", url)
        return response.get("data", [])

    def close(self) -> None:
        """Close the HTTP session and release all connections."""
        self._session.close()

    def fetch_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch all static data categories.

        Returns:
            Dict with keys: markets, products, instruments, prices, times
        """
        return {
            "markets": self.get_markets(),
            "products": self.get_products(),
            "instruments": self.get_instruments(),
            "prices": self.get_prices(),
            "times": self.get_times(),
        }
