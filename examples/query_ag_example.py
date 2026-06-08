"""Example Module - 查询 Ag（白银）相关静态数据.

此示例演示如何:
1. 作为 TycheModule 连接到 TycheEngine
2. 通过 Job 请求向 static_data 模块查询数据
3. 过滤并打印 Ag 相关的交易所、交易时段、期货合约和期权合约

启动顺序:
1. 先启动 TycheEngine: python main.py
2. 再启动 static_data 模块: python -m src.modules.static_data
3. 最后运行此示例: python examples/query_ag_example.py
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, List

# 确保项目根目录和 src 目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.tyche.module import TycheModule
from src.tyche.types import Endpoint

logger = logging.getLogger(__name__)

# 引擎端口布局 (基于 registration port 5555):
#   5555 - registration ROUTER
#   5556 - event XPUB
#   5559 - heartbeat PUB
#   5560 - heartbeat receive ROUTER
#   5564 - job ROUTER
ENGINE_PORT = 5555
HEARTBEAT_RECEIVE_PORT = ENGINE_PORT + 5  # 5560


class AgQueryModule(TycheModule):
    """示例模块：查询并展示 Ag（白银）相关静态数据."""

    def __init__(self):
        super().__init__(
            engine_endpoint=Endpoint("127.0.0.1", ENGINE_PORT),
            family_name="ag_query_example",
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", HEARTBEAT_RECEIVE_PORT),
        )
        self._stop_event = threading.Event()

    def run(self) -> None:
        """启动模块，执行查询，然后保持运行直到收到停止信号."""
        self.start()

        # 检查注册是否成功
        if not getattr(self, "_registered", False):
            logger.error("[%s] 注册失败，请检查引擎是否已启动且端口配置正确", self.module_id)
            self.stop()
            return

        logger.info("[%s] 模块已注册成功，等待连接稳定...", self.module_id)
        time.sleep(1)  # 等待连接稳定

        try:
            self._query_ag_data()
        except Exception as e:
            logger.error("查询 Ag 数据失败: %s", e)

        # 查询完成后自动退出（无需手动 Ctrl+C）
        logger.info("[%s] 查询完成，自动退出", self.module_id)
        self.stop()

    def stop(self) -> None:
        """停止模块."""
        self._stop_event.set()
        super().stop()

    def _query_ag_data(self) -> None:
        """执行 Ag 相关数据查询并打印结果."""
        logger.info("=" * 60)
        logger.info("开始查询 Ag（白银）相关静态数据")
        logger.info("=" * 60)

        # 1. 查询所有交易所，然后过滤出 Ag 相关的
        self._query_and_print_exchanges()

        # 2. 查询 Ag 相关的品种信息
        self._query_and_print_products()

        # 3. 查询 Ag 期货合约
        self._query_and_print_futures()

        # 4. 查询 Ag 期权合约
        self._query_and_print_options()

        # 5. 查询 Ag 相关交易时段
        self._query_and_print_trading_times()

        logger.info("=" * 60)
        logger.info("Ag 数据查询完成")
        logger.info("=" * 60)

    def _query_and_print_exchanges(self) -> None:
        """查询并打印 Ag 相关的交易所信息."""
        logger.info("\n【1. 交易所信息】")
        try:
            # 查询上海期货交易所 (SHFE) - Ag 白银在上海期货交易所交易
            result = self.request_event(
                "query_markets",
                {"exchange_id": "SHFE"},
                timeout=5.0,
            )
            logger.info("  原始返回: %s", json.dumps(result, ensure_ascii=False, indent=2)[:500])
            markets = result.get("result", {}).get("markets", [])
            if markets:
                logger.info("  Ag 白银所在交易所:")
                for m in markets:
                    logger.info("    - 交易所ID: %s", m.get("ExchangeID", "N/A"))
                    logger.info("      名称: %s", m.get("ExchangeName", "N/A"))
                    logger.info("      地区: %s", m.get("Area", "N/A"))
                    logger.info("      状态: %s", m.get("Status", "N/A"))
            else:
                logger.info("  未找到交易所数据")
        except Exception as e:
            logger.error("  查询交易所失败: %s", e)

    def _query_and_print_products(self) -> None:
        """查询并打印 Ag 相关的品种信息."""
        logger.info("\n【2. 品种信息】")
        try:
            # 查询上海期货交易所的品种
            result = self.request_event(
                "query_products",
                {"exchange_id": "SHFE"},
                timeout=5.0,
            )
            products = result.get("result", {}).get("products", [])
            # 过滤出 Ag 相关的品种（大小写不敏感）
            ag_products = [p for p in products if "ag" in str(p.get("ProductID", "")).lower()]
            if ag_products:
                logger.info("  Ag 相关品种:")
                for p in ag_products:
                    logger.info("    - 品种ID: %s", p.get("ProductID", "N/A"))
                    logger.info("      名称: %s", p.get("ProductName", "N/A"))
                    logger.info("      交易所: %s", p.get("ExchangeID", "N/A"))
                    logger.info("      类别: %s", p.get("ProductClass", "N/A"))
            else:
                logger.info("  未找到 Ag 相关品种，显示所有 SHFE 品种:")
                for p in products[:5]:  # 只显示前5个
                    logger.info("    - 品种ID: %s", p.get("ProductID", "N/A"))
        except Exception as e:
            logger.error("  查询品种失败: %s", e)

    def _query_and_print_futures(self) -> None:
        """查询并打印 Ag 期货合约."""
        logger.info("\n【3. 期货合约】")
        try:
            # 查询 Ag 期货合约 - ProductClass=1 表示期货
            result = self.request_event(
                "query_instruments",
                {
                    "exchange_id": "SHFE",
                    "product_id": "ag",
                    "product_class": "1",
                },
                timeout=5.0,
            )
            instruments = result.get("result", {}).get("instruments", [])
            if instruments:
                logger.info("  Ag 期货合约 (%d 个):", len(instruments))
                for inst in instruments[:10]:  # 显示前10个
                    logger.info("    - 合约ID: %s", inst.get("InstrumentID", "N/A"))
                    logger.info("      品种: %s", inst.get("ProductID", "N/A"))
                    logger.info("      到期日: %s", inst.get("ExpireDate", "N/A"))
                    logger.info("      状态: %s", inst.get("InstLifePhase", "N/A"))
                if len(instruments) > 10:
                    logger.info("    ... 还有 %d 个合约", len(instruments) - 10)
            else:
                # 尝试不带 product_id 过滤
                result = self.request_event(
                    "query_instruments",
                    {"exchange_id": "SHFE", "product_class": "1"},
                    timeout=5.0,
                )
                instruments = result.get("result", {}).get("instruments", [])
                # 手动过滤 Ag 相关合约
                ag_insts = [i for i in instruments if str(i.get("ProductID", "")).lower() == "ag"]
                if ag_insts:
                    logger.info("  Ag 期货合约 (%d 个):", len(ag_insts))
                    for inst in ag_insts[:10]:
                        logger.info("    - 合约ID: %s", inst.get("InstrumentID", "N/A"))
                else:
                    logger.info("  未找到 Ag 期货合约")
        except Exception as e:
            logger.error("  查询期货合约失败: %s", e)

    def _query_and_print_options(self) -> None:
        """查询并打印 Ag 期权合约."""
        logger.info("\n【4. 期权合约】")
        try:
            # 查询 Ag 期权合约 - ProductClass=2 表示期权
            # Ag 期权的 ProductID 是 "ag_o" 而不是 "ag"
            result = self.request_event(
                "query_instruments",
                {
                    "exchange_id": "SHFE",
                    "product_id": "ag_o",
                    "product_class": "2",
                },
                timeout=5.0,
            )
            instruments = result.get("result", {}).get("instruments", [])
            if instruments:
                logger.info("  Ag 期权合约 (%d 个):", len(instruments))
                for inst in instruments[:10]:
                    logger.info("    - 合约ID: %s", inst.get("InstrumentID", "N/A"))
                    logger.info("      品种: %s", inst.get("ProductID", "N/A"))
                    logger.info("      到期日: %s", inst.get("ExpireDate", "N/A"))
                    logger.info("      状态: %s", inst.get("InstLifePhase", "N/A"))
                if len(instruments) > 10:
                    logger.info("    ... 还有 %d 个合约", len(instruments) - 10)
            else:
                # 尝试不带 product_id 过滤
                result = self.request_event(
                    "query_instruments",
                    {"exchange_id": "SHFE", "product_class": "2"},
                    timeout=5.0,
                )
                instruments = result.get("result", {}).get("instruments", [])
                ag_insts = [i for i in instruments if str(i.get("ProductID", "")).lower() in ("ag_o", "ag")]
                if ag_insts:
                    logger.info("  Ag 期权合约 (%d 个):", len(ag_insts))
                    for inst in ag_insts[:10]:
                        logger.info("    - 合约ID: %s", inst.get("InstrumentID", "N/A"))
                else:
                    logger.info("  未找到 Ag 期权合约")
        except Exception as e:
            logger.error("  查询期权合约失败: %s", e)

    def _query_and_print_trading_times(self) -> None:
        """查询并打印 Ag 相关交易时段."""
        logger.info("\n【5. 交易时段】")
        try:
            # 查询 Ag 品种的交易时段
            result = self.request_event(
                "query_times",
                {"exchange_id": "SHFE", "product_id": "ag"},
                timeout=5.0,
            )
            times = result.get("result", {}).get("times", [])
            if times:
                logger.info("  Ag 交易时段 (%d 条):", len(times))
                for t in times[:5]:
                    logger.info("    - 交易所: %s", t.get("ExchangeID", "N/A"))
                    logger.info("      品种: %s", t.get("ProductID", "N/A"))
                    logger.info("      时段: %s - %s",
                               t.get("TimeBegin", "N/A"),
                               t.get("TimeEnd", "N/A"))
                    logger.info("      时段序号: %s", t.get("SegmentNo", "N/A"))
                    logger.info("      类别: %s", t.get("ProductClass", "N/A"))
            else:
                # 查询 SHFE 所有交易时段
                result = self.request_event(
                    "query_times",
                    {"exchange_id": "SHFE"},
                    timeout=5.0,
                )
                times = result.get("result", {}).get("times", [])
                logger.info("  SHFE 交易时段 (%d 条):", len(times))
                for t in times[:5]:
                    logger.info("    - 品种: %s, 时段: %s - %s",
                               t.get("ProductID", "N/A"),
                               t.get("TimeBegin", "N/A"),
                               t.get("TimeEnd", "N/A"))
        except Exception as e:
            logger.error("  查询交易时段失败: %s", e)


def main() -> None:
    """主函数."""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    module = AgQueryModule()

    def _signal_handler(signum: int, _frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s，正在停止...", sig_name)
        module.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        module.run()
    except Exception as e:
        logger.exception("模块运行异常: %s", e)
        raise
    finally:
        logger.info("模块已停止")


if __name__ == "__main__":
    main()
