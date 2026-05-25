"""OpenCTP Gateway Module 入口 — 支持 ``python -m src.modules.openctp_gateway`` 启动."""

import argparse
import atexit
import logging
import os
import signal
import sys
import threading

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="启动 OpenCTP Gateway 模块",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="JSON 配置文件路径",
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
    from src.modules.openctp_gateway.config import GatewayConfig

    config = GatewayConfig.from_file(args.config)
    logger.info(
        "Gateway 配置: type=%s, md_front=%s, td_front=%s, engine=%s:%d",
        config.gateway_type,
        config.md_front,
        config.td_front,
        config.engine_host,
        config.engine_port,
    )

    # ── DLL Loading (MUST happen before importing gateway) ───────
    from src.modules.openctp_gateway.dll_loader import load_api

    md_module, td_module = load_api(config.gateway_type)

    # ── Instantiate Gateway ──────────────────────────────────────
    from src.modules.openctp_gateway.gateway import OpenCtpGateway

    module = OpenCtpGateway(config, md_module, td_module)
    stop_event = threading.Event()
    _cleanup_done = False

    def _do_cleanup() -> None:
        """确保 module.stop() 被调用（atexit 兜底）."""
        nonlocal _cleanup_done
        if _cleanup_done:
            return
        _cleanup_done = True
        try:
            module.stop()
        except Exception:
            pass
        logger.info("OpenCTP Gateway 模块已停止")

    atexit.register(_do_cleanup)

    def _shutdown(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s，正在停止 OpenCTP Gateway...", sig_name)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Start ────────────────────────────────────────────────────
    try:
        module.start()
        logger.info("OpenCTP Gateway 已启动，按 Ctrl+C 停止")
        # Use polling with timeout to allow Ctrl+C on Windows
        while not stop_event.is_set():
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        logger.info("收到 KeyboardInterrupt，正在停止 OpenCTP Gateway...")
    except Exception:
        logger.exception("OpenCTP Gateway 运行异常")
    finally:
        _do_cleanup()
        # 强制退出：CTP API 内部线程可能阻止进程退出
        os._exit(0)


if __name__ == "__main__":
    main()
