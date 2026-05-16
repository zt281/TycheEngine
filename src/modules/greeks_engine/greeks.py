"""Greeks Engine 模块 - 实时期权 Greeks 计算与发布.

接收行情事件，对期权合约实时计算隐含波动率和全量 Greeks，
并通过 greeks_update 事件发布给下游消费者。
"""

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from tyche.module import TycheModule
from tyche.types import Endpoint

from .bs_model import bs_greeks, implied_vol
from .config import GreeksConfig

logger = logging.getLogger(__name__)

# CTP 行情中无效价格的标志值
_CTP_DBL_MAX = 1.7976931348623157e+308


class GreeksEngine(TycheModule):
    """实时 Greeks 计算引擎.

    继承 TycheModule，通过 on_quote 自动订阅行情事件，
    当收到期权 tick 时计算 IV 和 Greeks 并通过 greeks_update 事件发布。

    配置支持 underlyings (exchange_id -> [product_ids]) 格式，
    启动时自动从 static_data 模块查询期货和期权合约列表，
    构建 underlying_map、expiry_map 和 underlying_instruments。
    """

    def __init__(self, config: GreeksConfig, family_name: str = "greeks_engine"):
        super().__init__(
            engine_endpoint=Endpoint(config.engine_host, config.engine_port),
            family_name=family_name,
        )
        self.config = config
        # 标的最新价缓存: instrument_id -> last_price
        self.underlying_prices: Dict[str, float] = {}

    def start(self) -> None:
        """启动模块: 先注册到引擎，然后从 static_data 解析合约列表."""
        super().start()
        self._resolve_instruments()
        logger.info(
            "GreeksEngine 启动完成: 监听标的 %d 个, 期权映射 %d 条",
            len(self.config.underlying_instruments),
            len(self.config.underlying_map),
        )

    def _resolve_instruments(self) -> None:
        """从 static_data 查询期货和期权合约，构建 Greeks 所需映射.

        对每个 exchange_id -> [product_ids]:
        1. 查询期货合约 -> 加入 underlying_instruments
        2. 查询期权合约 -> 构建 underlying_map 和 expiry_map

        期权 product_id 按交易所规则推导:
            - SHFE/DCE/INE/GFEX: {product_id}_o
            - CZCE: {product_id}C 或 {product_id}P
            - CFFEX: 与期货相同 (IO, HO, MO)
        """
        if not self.config.underlyings:
            logger.warning(
                "[GreeksEngine] No underlyings configured, "
                "nothing to resolve"
            )
            return

        for exchange_id, product_ids in self.config.underlyings.items():
            for product_id in product_ids:
                # 1. 查询期货合约 (标的)
                future_payload = {
                    "exchange_id": exchange_id,
                    "product_id": product_id,
                    "product_class": "1",
                }
                future_instruments = self._query_instruments(
                    exchange_id, product_id, future_payload
                )
                for inst in future_instruments:
                    inst_id = inst.get("InstrumentID", "")
                    if inst_id:
                        self.config.underlying_instruments.add(inst_id)

                # 2. 查询期权合约
                option_product_ids: List[str] = []
                if exchange_id in ("SHFE", "DCE", "INE", "GFEX"):
                    option_product_ids = [f"{product_id}_o"]
                elif exchange_id == "CZCE":
                    option_product_ids = [f"{product_id}C", f"{product_id}P"]
                elif exchange_id == "CFFEX":
                    option_product_ids = [product_id]

                for opt_pid in option_product_ids:
                    if not opt_pid:
                        continue
                    option_payload = {
                        "exchange_id": exchange_id,
                        "product_id": opt_pid,
                        "product_class": "2",
                    }
                    option_instruments = self._query_instruments(
                        exchange_id, opt_pid, option_payload
                    )
                    for inst in option_instruments:
                        inst_id = inst.get("InstrumentID", "")
                        underlying_id = inst.get("UnderlyingInstrID", "")
                        expire_date = inst.get("ExpireDate", "")
                        if inst_id and underlying_id and expire_date:
                            self.config.underlying_map[inst_id] = underlying_id
                            self.config.expiry_map[inst_id] = expire_date

    def _query_instruments(
        self, exchange_id: str, product_id: str, payload: dict
    ) -> List[Dict[str, Any]]:
        """发送 query_instruments job 请求并返回合约列表."""
        logger.info(
            "[GreeksEngine] Querying static_data for: "
            "product_id=%s, exchange_id=%s",
            product_id,
            exchange_id,
        )

        try:
            result = self.request_event(
                "query_instruments",
                payload,
                timeout=self.config.resolve_timeout,
            )
        except TimeoutError:
            logger.error(
                "[GreeksEngine] Timeout querying static_data for "
                "product_id=%s, exchange_id=%s — skipping",
                product_id,
                exchange_id,
            )
            return []
        except Exception as e:
            logger.error(
                "[GreeksEngine] Error querying static_data for "
                "product_id=%s, exchange_id=%s: %s — skipping",
                product_id,
                exchange_id,
                e,
            )
            return []

        # request_event wraps handler return value in {"result": ...}
        if "error" in result:
            logger.error(
                "[GreeksEngine] query_instruments returned error "
                "for product_id=%s, exchange_id=%s: %s",
                product_id,
                exchange_id,
                result["error"],
            )
            return []

        inner = result.get("result", {})
        instruments = inner.get("instruments", [])
        logger.info(
            "[GreeksEngine] Resolved %d instruments for "
            "product_id=%s, exchange_id=%s",
            len(instruments),
            product_id,
            exchange_id,
        )
        return instruments

    # ── Broadcast Event Consumer ───────────────────────────────────

    def on_quote(self, payload: Dict[str, Any]) -> None:
        """接收行情广播事件 - 自动订阅 quote topic.

        仅处理标的(期货) tick，更新本地 underlying_prices 缓存。
        所有 GreeksEngine 实例都会收到并独立更新缓存。
        """
        instrument_id = payload.get("instrument_id", "")

        if instrument_id in self.config.underlying_instruments:
            old_price = self.underlying_prices.get(instrument_id)
            self.underlying_prices[instrument_id] = payload["last_price"]
            if old_price is None:
                logger.info(
                    "标的首次价格: %s = %.2f",
                    instrument_id,
                    payload["last_price"],
                )
            else:
                logger.debug(
                    "标的价格更新: %s = %.2f (prev=%.2f)",
                    instrument_id,
                    payload["last_price"],
                    old_price,
                )

    # ── Job Handler (round-robin dispatch) ─────────────────────────

    def handle_compute_greeks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理期权 Greeks 计算任务 - 通过 job router 轮询分发.

        每次只有一个 GreeksEngine 实例会收到并处理该任务。
        计算完成后返回结果，同时通过事件发布给下游。
        """
        instrument_id = payload.get("instrument_id", "")

        # CTP 返回的期权合约 ID 可能包含 '-' (如 ag2506-C-6000)
        # 需要转换为配置中的格式 (如 ag2506C6000)
        normalized_id = self._normalize_option_id(instrument_id)

        if normalized_id not in self.config.underlying_map:
            logger.debug("跳过非期权合约: %s (normalized=%s)", instrument_id, normalized_id)
            return {"status": "skipped", "reason": "not_an_option"}

        result = self._compute_and_publish_greeks(normalized_id, payload)
        if result:
            logger.info("Greeks 计算完成: %s", instrument_id)
        return {"status": "ok", "instrument_id": instrument_id}

    @staticmethod
    def _normalize_option_id(instrument_id: str) -> str:
        """将 CTP 期权合约 ID 转换为配置中的格式.

        CTP 格式: ag2506-C-6000, ag2506-P-6000
        配置格式: ag2506C6000, ag2506P6000
        """
        parts = instrument_id.split("-")
        if len(parts) == 3:
            # CTP 格式: {underlying}{month}-{C/P}-{strike}
            return f"{parts[0]}{parts[1]}{parts[2]}"
        return instrument_id

    # ── Event Producer ─────────────────────────────────────────────

    def send_greeks_update(self, payload: Dict[str, Any]) -> None:
        """声明 greeks_update 事件生产者 - 自动发现."""
        self.send_event("greeks_update", payload)

    # ── Internal ───────────────────────────────────────────────────

    def _compute_and_publish_greeks(
        self, instrument_id: str, tick: Dict[str, Any]
    ) -> bool:
        """计算并发布 Greeks.

        流程:
        1. 获取标的价格
        2. 解析合约信息（行权价、到期时间、call/put）
        3. 计算 IV
        4. 计算 Greeks
        5. 发布 greeks_update 事件
        """
        # 1. 获取标的合约 ID 和标的价格
        underlying_id = self.config.underlying_map[instrument_id]
        underlying_price = self.underlying_prices.get(underlying_id)

        if underlying_price is None:
            logger.warning(
                "标的价格尚未收到，跳过 Greeks 计算: %s -> %s",
                instrument_id,
                underlying_id,
            )
            return False

        # 2. 获取市场价格并验证
        market_price = tick.get("last_price", 0.0)
        if market_price <= 0.0 or market_price >= _CTP_DBL_MAX:
            logger.warning(
                "无效市场价格，跳过 Greeks 计算: %s price=%.4f",
                instrument_id,
                market_price,
            )
            return False

        # 3. 解析合约信息
        strike = self._parse_strike(instrument_id)
        is_call = self._parse_is_call(instrument_id)
        expiry_str = self.config.expiry_map.get(instrument_id)

        if strike is None or is_call is None or expiry_str is None:
            logger.warning(
                "无法解析合约信息，跳过: %s", instrument_id
            )
            return False

        # 4. 计算年化到期时间
        T = self._calc_time_to_expiry(expiry_str)
        if T <= 0.0:
            logger.warning(
                "期权已到期，跳过: %s expiry=%s", instrument_id, expiry_str
            )
            return False

        # 5. 计算 IV
        r = self.config.risk_free_rate
        iv = implied_vol(market_price, underlying_price, strike, T, r, is_call)

        if iv < 0.0:
            logger.warning(
                "IV 求解失败: %s market_price=%.4f S=%.2f K=%.2f T=%.4f r=%.4f %s",
                instrument_id,
                market_price,
                underlying_price,
                strike,
                T,
                r,
                "Call" if is_call else "Put",
            )
            return False

        # 6. 计算全量 Greeks
        price, delta, gamma, vega, theta, rho = bs_greeks(
            underlying_price, strike, T, r, iv, is_call
        )

        # 7. 发布 greeks_update 事件
        greeks_payload = {
            "instrument_id": instrument_id,
            "underlying_id": underlying_id,
            "underlying_price": underlying_price,
            "strike": strike,
            "expiry": expiry_str,
            "is_call": is_call,
            "market_price": market_price,
            "implied_vol": round(iv, 6),
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega, 4),
            "theta": round(theta, 4),
            "rho": round(rho, 4),
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        }

        self.send_greeks_update(greeks_payload)
        logger.info(
            "Greeks 发布: %s IV=%.4f delta=%.4f gamma=%.6f vega=%.4f theta=%.4f",
            instrument_id,
            iv,
            delta,
            gamma,
            vega,
            theta,
        )

    @staticmethod
    def _parse_strike(instrument_id: str) -> Optional[float]:
        """从合约 ID 解析行权价.

        支持两种格式:
        - CTP 格式: IO2412-C-4000, ag2506-C-6000
          行权价为最后一个 '-' 分隔符后的数值
        - CZCE 格式: TA608C6700, TA608P6700
          行权价为 'C' 或 'P' 后的数值
        """
        # 尝试 CTP 格式 (带 '-')
        parts = instrument_id.split("-")
        if len(parts) >= 3:
            try:
                return float(parts[-1])
            except ValueError:
                return None

        # 尝试 CZCE 格式 (无 '-', 如 TA608C6700)
        # 找到 'C' 或 'P' 的位置，其后为行权价
        upper_id = instrument_id.upper()
        for flag in ("C", "P"):
            # 从后往前找最后一个 C/P，避免 product_id 中的字母干扰
            pos = upper_id.rfind(flag)
            if pos > 0:
                try:
                    return float(instrument_id[pos + 1 :])
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_is_call(instrument_id: str) -> Optional[bool]:
        """从合约 ID 解析看涨/看跌.

        支持两种格式:
        - CTP 格式: IO2412-C-4000 (Call), IO2412-P-3800 (Put)
        - CZCE 格式: TA608C6700 (Call), TA608P6700 (Put)
        """
        # 尝试 CTP 格式 (带 '-')
        parts = instrument_id.split("-")
        if len(parts) >= 3:
            flag = parts[-2].upper()
            if flag == "C":
                return True
            elif flag == "P":
                return False
            return None

        # 尝试 CZCE 格式 (无 '-', 如 TA608C6700)
        # 从后往前找最后一个 'C' 或 'P' 的位置
        upper_id = instrument_id.upper()
        c_pos = upper_id.rfind("C")
        p_pos = upper_id.rfind("P")

        if c_pos > 0 and (p_pos < 0 or c_pos > p_pos):
            return True
        if p_pos > 0 and (c_pos < 0 or p_pos > c_pos):
            return False
        return None

    @staticmethod
    def _calc_time_to_expiry(expiry_str: str) -> float:
        """计算年化到期时间.

        Args:
            expiry_str: 到期日字符串，格式 "YYYY-MM-DD"

        Returns:
            年化时间差 T = days_remaining / 365.0
        """
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            today = date.today()
            days_remaining = (expiry_date - today).days
            if days_remaining <= 0:
                return 0.0
            return days_remaining / 365.0
        except (ValueError, TypeError):
            return 0.0
