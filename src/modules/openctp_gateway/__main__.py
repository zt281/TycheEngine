"""OpenCTP Gateway 模块入口 — 支持 ``python -m modules.openctp_gateway`` 启动."""

import argparse
import json
import logging
import signal
import threading
from typing import Optional

from .config import GatewayConfig
from .gateway import OpenCtpGateway

logger = logging.getLogger(__name__)


def _load_config(config_path: Optional[str]) -> GatewayConfig:
    """从 JSON 配置文件构建 GatewayConfig.

    配置文件格式:
        {
            "engine": {"host": "127.0.0.1", "port": 5555},
            "gateway": {
                "md_front": "tcp://122.51.136.165:20004",
                "td_front": "tcp://122.51.136.165:20002",
                "broker_id": "",
                "user_id": "test",
                "password": "test",
                "underlyings": {
                    "SHFE": ["ag", "cu"],
                    "CFFEX": ["IF", "IC"]
                },
                "subscribe_options": false,
                "resolve_timeout": 10.0
            }
        }

        subscribe_options: 是否同时订阅期权合约（ProductClass=2）。
            为 true 时，会对每个 underlying 额外查询并订阅其期权合约
            （期权品种ID自动加上 ``_o`` 后缀，如 ``ag`` -> ``ag_o``）。
    """
    if config_path is None:
        return GatewayConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    gw_cfg = raw.get("gateway", {})
    engine_cfg = raw.get("engine", {})

    # Parse underlyings dict (exchange_id -> list of product_ids)
    underlyings: dict = {}
    for exchange_id, product_ids in gw_cfg.get("underlyings", {}).items():
        underlyings[exchange_id] = list(product_ids)

    return GatewayConfig(
        md_front=gw_cfg.get("md_front", GatewayConfig.md_front),
        td_front=gw_cfg.get("td_front", GatewayConfig.td_front),
        broker_id=gw_cfg.get("broker_id", GatewayConfig.broker_id),
        user_id=gw_cfg.get("user_id", GatewayConfig.user_id),
        password=gw_cfg.get("password", GatewayConfig.password),
        underlyings=underlyings,
        subscribe_options=gw_cfg.get("subscribe_options", GatewayConfig.subscribe_options),
        engine_host=engine_cfg.get("host", GatewayConfig.engine_host),
        engine_port=engine_cfg.get("port", GatewayConfig.engine_port),
        resolve_timeout=gw_cfg.get("resolve_timeout", GatewayConfig.resolve_timeout),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="启动 OpenCTP Gateway 模块",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="JSON 配置文件路径 (可选，默认使用 GatewayConfig 默认值)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认 INFO)",
    )
    args = parser.parse_args()

    # ── Logging ──────────────────────────────────────────────────
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Config ───────────────────────────────────────────────────
    config = _load_config(args.config)
    underlying_summary = [
        f"{pid}@{eid}"
        for eid, pids in config.underlyings.items()
        for pid in pids
    ]
    logger.info(
        "OpenCTP Gateway 配置: md_front=%s, td_front=%s, "
        "underlyings=[%s], subscribe_options=%s, engine=%s:%d",
        config.md_front,
        config.td_front,
        ", ".join(underlying_summary),
        config.subscribe_options,
        config.engine_host,
        config.engine_port,
    )

    # ── Start ────────────────────────────────────────────────────
    gateway = OpenCtpGateway(config)
    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:  # noqa: ANN001
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s，正在停止 Gateway...", sig_name)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        gateway.start()
        logger.info("OpenCTP Gateway 已启动，按 Ctrl+C 停止")
        # Use polling with timeout to allow Ctrl+C on Windows
        while not stop_event.is_set():
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，正在停止 Gateway...")
    except Exception:
        logger.exception("Gateway 运行异常")
    finally:
        gateway.stop()
        logger.info("OpenCTP Gateway 已停止")


if __name__ == "__main__":
    main()
