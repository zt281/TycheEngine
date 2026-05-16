"""Greeks Engine 模块入口 — 支持 ``python -m modules.greeks_engine`` 启动."""

import argparse
import json
import logging
import signal
import threading
from typing import Optional

from .config import GreeksConfig
from .greeks import GreeksEngine

logger = logging.getLogger(__name__)


def _load_config(config_path: Optional[str]) -> GreeksConfig:
    """从 JSON 配置文件构建 GreeksConfig.

    配置文件格式参见 ``examples/greeks_pipeline_config.json``.
    ``greeks`` 段映射到 GreeksConfig 字段，
    ``engine`` 段的 host/port 覆盖 engine_host / engine_port.
    """
    if config_path is None:
        logger.info("未提供配置文件，使用 GreeksConfig 默认值")
        return GreeksConfig()

    logger.info("加载配置文件: %s", config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    gk_cfg = raw.get("greeks", {})
    engine_cfg = raw.get("engine", {})

    config = GreeksConfig(
        risk_free_rate=gk_cfg.get("risk_free_rate", GreeksConfig.risk_free_rate),
        underlyings=gk_cfg.get("underlyings", {}),
        engine_host=engine_cfg.get("host", GreeksConfig.engine_host),
        engine_port=engine_cfg.get("port", GreeksConfig.engine_port),
        resolve_timeout=gk_cfg.get("resolve_timeout", GreeksConfig.resolve_timeout),
    )
    logger.info(
        "配置加载完成: underlyings %d 个交易所",
        len(config.underlyings),
    )
    return config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="启动 Greeks Engine 模块",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="JSON 配置文件路径 (可选，默认使用 GreeksConfig 默认值)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认 INFO)",
    )
    parser.add_argument(
        "--module-id",
        type=str,
        default="greeks_engine",
        help="模块 family_name (默认 greeks_engine，多实例可设不同名称)",
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
    logger.info(
        "Greeks Engine 配置汇总: risk_free_rate=%.4f, engine=%s:%d",
        config.risk_free_rate,
        config.engine_host,
        config.engine_port,
    )

    # ── Start ────────────────────────────────────────────────────
    engine = GreeksEngine(config, family_name=args.module_id)
    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:  # noqa: ANN001
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s，正在停止 Greeks Engine...", sig_name)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        engine.start()
        logger.info("Greeks Engine (%s) 已启动，监听 engine %s:%d，按 Ctrl+C 停止", args.module_id, config.engine_host, config.engine_port)
        # Use polling with timeout to allow Ctrl+C on Windows
        while not stop_event.is_set():
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，正在停止 Greeks Engine...")
    except Exception:
        logger.exception("Greeks Engine 运行异常")
    finally:
        logger.info("正在停止 Greeks Engine...")
        engine.stop()
        logger.info("Greeks Engine 已停止")


if __name__ == "__main__":
    main()
