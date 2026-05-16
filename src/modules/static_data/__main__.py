"""Static Data Module 入口 — 支持 ``python -m modules.static_data`` 启动."""

import argparse
import json
import logging
import signal
import threading
from typing import Optional

from .config import StaticDataConfig
from .static_data import StaticDataModule

logger = logging.getLogger(__name__)


def _load_config(config_path: Optional[str]) -> StaticDataConfig:
    """从 JSON 配置文件构建 StaticDataConfig.

    配置文件格式:
        {
            "engine": {"host": "127.0.0.1", "port": 20550},
            "static_data": {
                "base_url": "http://dict.openctp.cn",
                "refresh_interval": 21600,
                "data_dir": "data/static",
                "areas": ["China"],
                "types": ["futures", "option"],
                "markets": [],
                "products": [],
                "instruments": [],
                "request_timeout": 30,
                "retry_count": 3,
                "retry_delay": 5
            }
        }
    """
    if config_path is None:
        return StaticDataConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    sd_cfg = raw.get("static_data", {})
    engine_cfg = raw.get("engine", {})

    defaults = StaticDataConfig()
    return StaticDataConfig(
        base_url=sd_cfg.get("base_url", defaults.base_url),
        refresh_interval=sd_cfg.get("refresh_interval", defaults.refresh_interval),
        data_dir=sd_cfg.get("data_dir", defaults.data_dir),
        engine_host=engine_cfg.get("host", defaults.engine_host),
        engine_port=engine_cfg.get("port", defaults.engine_port),
        areas=sd_cfg.get("areas", defaults.areas),
        types=sd_cfg.get("types", defaults.types),
        markets=sd_cfg.get("markets", defaults.markets),
        products=sd_cfg.get("products", defaults.products),
        instruments=sd_cfg.get("instruments", defaults.instruments),
        request_timeout=sd_cfg.get("request_timeout", defaults.request_timeout),
        retry_count=sd_cfg.get("retry_count", defaults.retry_count),
        retry_delay=sd_cfg.get("retry_delay", defaults.retry_delay),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="启动 Static Data 模块",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="JSON 配置文件路径 (可选，默认使用 StaticDataConfig 默认值)",
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
    logger.info(
        "Static Data 配置: base_url=%s, refresh_interval=%ds, data_dir=%s, "
        "engine=%s:%d",
        config.base_url,
        config.refresh_interval,
        config.data_dir,
        config.engine_host,
        config.engine_port,
    )

    # ── Start ────────────────────────────────────────────────────
    module = StaticDataModule(config)
    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:  # noqa: ANN001
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s，正在停止 Static Data 模块...", sig_name)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        module.start()
        logger.info("Static Data 模块已启动，按 Ctrl+C 停止")
        # Use polling with timeout to allow Ctrl+C on Windows
        while not stop_event.is_set():
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，正在停止 Static Data 模块...")
    except Exception:
        logger.exception("Static Data 模块运行异常")
    finally:
        module.stop()
        logger.info("Static Data 模块已停止")


if __name__ == "__main__":
    main()
