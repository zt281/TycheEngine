#!/usr/bin/env python3
"""Standalone CTP gateway process entry point.

Loads configuration, instantiates sim or live gateway, connects to CTP
and TycheEngine, and blocks until shutdown signal.

Usage:
    python -m modules.trading.gateway.ctp.gateway_main --config gateway.json
    python -m modules.trading.gateway.ctp.gateway_main --sim --user-id ID --password PASS
"""

import argparse
import logging
import signal
import sys
import time
from typing import Any, Dict, Optional

from modules.trading.gateway.ctp.config import GatewayConfig, GatewayType, load_config
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a CTP gateway as a standalone process.")
    parser.add_argument("--config", help="Path to JSON config file.")
    parser.add_argument("--sim", action="store_true", help="Simulated mode (OpenCTP).")
    parser.add_argument("--live", action="store_true", help="Live broker mode.")
    parser.add_argument("--engine-host", default="127.0.0.1", help="TycheEngine host.")
    parser.add_argument("--engine-port", type=int, default=5555, help="TycheEngine registration port.")
    parser.add_argument("--engine-hb-port", type=int, default=5559, help="TycheEngine heartbeat port.")
    parser.add_argument("--user-id", help="Trading account user ID.")
    parser.add_argument("--password", help="Trading account password.")
    parser.add_argument("--broker-id", default="9999", help="CTP broker ID.")
    parser.add_argument("--env", default="7x24", choices=["7x24", "sim"], help="OpenCTP environment.")
    parser.add_argument("--td-front", help="Trading front address (live mode only).")
    parser.add_argument("--md-front", help="Market-data front address (live mode only).")
    parser.add_argument("--auth-code", help="Broker auth code (live mode only).")
    parser.add_argument("--app-id", help="Application ID (live mode only).")
    parser.add_argument("--instruments", nargs="+", default=["rb2410"], help="Instrument symbols to subscribe.")
    parser.add_argument("--flow-path", default="./ctp_flow", help="CTP flow file directory.")
    return parser.parse_args(argv)


def _cli_args_to_dict(args: argparse.Namespace) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    if args.user_id:
        overrides["user_id"] = args.user_id
    if args.password:
        overrides["password"] = args.password
    if args.broker_id != "9999":
        overrides["broker_id"] = args.broker_id
    if args.instruments != ["rb2410"]:
        overrides["instruments"] = args.instruments
    return overrides


def build_gateway(config_path: Optional[str], cli_overrides: Dict[str, Any]) -> Any:
    if config_path:
        cfg = load_config(config_path, cli_args=cli_overrides)
    else:
        args = parse_args()
        gateway_type = GatewayType.LIVE if args.live else GatewayType.SIM
        cfg = GatewayConfig(
            gateway_type=gateway_type,
            engine_host=args.engine_host,
            engine_registration_port=args.engine_port,
            engine_heartbeat_port=args.engine_hb_port,
            sim_user_id=args.user_id or "",
            sim_password=args.password or "",
            sim_env=args.env,
            sim_broker_id=args.broker_id,
            live_user_id=args.user_id or "",
            live_password=args.password or "",
            live_broker_id=args.broker_id,
            live_td_front=args.td_front or "",
            live_md_front=args.md_front or "",
            live_auth_code=args.auth_code,
            live_app_id=args.app_id,
            instruments=args.instruments,
        )

    engine_endpoint = Endpoint(cfg.engine_host, cfg.engine_registration_port)
    heartbeat_endpoint = Endpoint(cfg.engine_host, cfg.engine_heartbeat_port)
    heartbeat_receive_endpoint = Endpoint(cfg.engine_host, cfg.engine_heartbeat_port + 1)

    kwargs = {
        "engine_endpoint": engine_endpoint,
        "heartbeat_endpoint": heartbeat_endpoint,
        "heartbeat_receive_endpoint": heartbeat_receive_endpoint,
    }

    if cfg.gateway_type == GatewayType.SIM:
        from modules.trading.gateway.ctp.sim import CtpSimGateway
        return CtpSimGateway(
            user_id=cfg.sim_user_id,
            password=cfg.sim_password,
            env=cfg.sim_env,
            broker_id=cfg.sim_broker_id,
            **kwargs,
        )
    else:
        from modules.trading.gateway.ctp.live import CtpLiveGateway
        return CtpLiveGateway(
            broker_id=cfg.live_broker_id,
            user_id=cfg.live_user_id,
            password=cfg.live_password,
            td_front=cfg.live_td_front,
            md_front=cfg.live_md_front,
            auth_code=cfg.live_auth_code,
            app_id=cfg.live_app_id,
            **kwargs,
        )


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
    )
    cli_overrides = _cli_args_to_dict(args)
    gateway = build_gateway(args.config, cli_overrides)
    venue = gateway.venue_name
    instrument_ids = [f"{sym}.{venue}.futures" for sym in gateway._subscribed_instruments or args.instruments]
    logger.info("Starting CTP gateway (venue=%s, id=%s)", gateway.venue_name, gateway.module_id)
    gateway.start_nonblocking()
    time.sleep(0.5)
    gateway.connect()
    if instrument_ids:
        gateway.subscribe_market_data(instrument_ids)
        logger.info("Subscribed to: %s", instrument_ids)

    def _shutdown(signum: int, frame: Any) -> None:
        logger.info("Received signal %d, shutting down...", signum)
        gateway.disconnect()
        gateway.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    logger.info("Gateway running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
