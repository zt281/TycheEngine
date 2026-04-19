#!/usr/bin/env python3
"""Example: Run a CTP gateway (simulated or live) as a standalone process.

Supports two modes:
  - **sim** (default): Connects to OpenCTP's free 7×24 or regular-hours simulation
    servers.  Only requires an OpenCTP account (register at https://openctp.cn).
  - **live**: Connects to a real CTP broker frontend.  Requires broker-issued
    credentials including front addresses and (usually) an auth code.

Start the engine first, then run this script to connect and stream market data.

Usage examples
--------------
# Terminal 1: Start engine
python examples/run_engine.py

# Terminal 2a: Simulated gateway (OpenCTP 7×24)
python examples/run_ctp_gateway.py --mode sim \
    --user-id YOUR_OPENCTP_ID --password YOUR_PASSWORD \
    --instruments rb2510 au2512

# Terminal 2b: Simulated gateway (regular-hours environment)
python examples/run_ctp_gateway.py --mode sim \
    --user-id YOUR_OPENCTP_ID --password YOUR_PASSWORD \
    --env sim --instruments rb2510

# Terminal 2c: Live gateway (real broker)
python examples/run_ctp_gateway.py --mode live \
    --broker-id 9999 --user-id ACCOUNT --password PWD \
    --td-front tcp://180.168.146.187:10201 \
    --md-front tcp://180.168.146.187:10211 \
    --auth-code AUTH --app-id APP \
    --instruments rb2510 IF2506

# Terminal 3: Start strategy (or any other consuming module)
python examples/run_strategy.py
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from modules.trading.gateway.ctp.live import CtpLiveGateway
from modules.trading.gateway.ctp.sim import CtpSimGateway
from tyche.types import Endpoint

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a CTP gateway module (simulated via OpenCTP or live broker).",
    )

    # --- Common options ---
    parser.add_argument(
        "--mode", choices=["sim", "live"], default="sim",
        help="Gateway mode: 'sim' for OpenCTP simulation (default), 'live' for real broker.",
    )
    parser.add_argument(
        "--instruments", nargs="+", default=["rb2510", "au2512"],
        help="Instrument symbols to subscribe, e.g. rb2510 IF2506 (default: rb2510 au2512).",
    )
    parser.add_argument(
        "--engine-host", default="127.0.0.1",
        help="TycheEngine host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--engine-port", type=int, default=5555,
        help="TycheEngine registration port (default: 5555).",
    )

    # --- Sim-mode options ---
    sim_group = parser.add_argument_group("Simulated mode (OpenCTP)")
    sim_group.add_argument(
        "--env", choices=["7x24", "sim"], default="7x24",
        help="OpenCTP environment: '7x24' (round-the-clock, default) or 'sim' (regular hours).",
    )

    # --- Live-mode options ---
    live_group = parser.add_argument_group("Live mode (real broker)")
    live_group.add_argument("--td-front", help="Trading front address, e.g. tcp://180.168.146.187:10201.")
    live_group.add_argument("--md-front", help="Market-data front address.")
    live_group.add_argument("--auth-code", help="Broker-issued authentication code.")
    live_group.add_argument("--app-id", help="Application ID registered with the broker.")

    # --- Shared credentials ---
    cred_group = parser.add_argument_group("Credentials (required for both modes)")
    cred_group.add_argument("--broker-id", default="9999", help="CTP broker ID (default: 9999).")
    cred_group.add_argument("--user-id", required=True, help="Trading account user ID.")
    cred_group.add_argument("--password", required=True, help="Trading account password.")

    args = parser.parse_args()

    # Validate live-mode requirements
    if args.mode == "live":
        if not args.td_front or not args.md_front:
            parser.error("Live mode requires --td-front and --md-front.")

    return args


def main() -> None:
    args = parse_args()

    engine_endpoint = Endpoint(args.engine_host, args.engine_port)

    # Build instrument IDs in TycheEngine format: <symbol>.<venue>.futures
    if args.mode == "sim":
        venue = "openctp"
    else:
        venue = "ctp"
    instrument_ids = [f"{sym}.{venue}.futures" for sym in args.instruments]

    print("=" * 66)
    print(f"  TycheEngine - CTP Gateway ({args.mode.upper()} mode)")
    print("=" * 66)
    print()

    # --- Create gateway ---
    if args.mode == "sim":
        gateway: CtpSimGateway | CtpLiveGateway = CtpSimGateway(
            engine_endpoint=engine_endpoint,
            user_id=args.user_id,
            password=args.password,
            env=args.env,
            broker_id=args.broker_id,
        )
        env_info = f"OpenCTP {args.env} environment"
        fronts = CtpSimGateway.ENVS[args.env]
        print(f"  Environment : {env_info}")
        print(f"  TD front    : {fronts['td_front']}")
        print(f"  MD front    : {fronts['md_front']}")
    else:
        gateway = CtpLiveGateway(
            engine_endpoint=engine_endpoint,
            broker_id=args.broker_id,
            user_id=args.user_id,
            password=args.password,
            td_front=args.td_front,
            md_front=args.md_front,
            auth_code=args.auth_code,
            app_id=args.app_id,
        )
        print(f"  TD front    : {args.td_front}")
        print(f"  MD front    : {args.md_front}")
        if args.auth_code:
            print(f"  Auth        : enabled (app_id={args.app_id})")

    print(f"  Broker ID   : {args.broker_id}")
    print(f"  User ID     : {args.user_id}")
    print(f"  Gateway ID  : {gateway.module_id}")
    print(f"  Venue       : {gateway.venue_name}")
    print(f"  Instruments : {', '.join(args.instruments)}")
    print()
    print(f"  Connecting to engine at tcp://{args.engine_host}:{args.engine_port}")
    print("  Press Ctrl+C to stop")
    print()

    try:
        # Start the module (registers with engine)
        gateway.start_nonblocking()
        time.sleep(1)

        # Connect to CTP front servers and log in
        print("Connecting to CTP front servers...")
        gateway.connect()

        # Subscribe to market data
        print(f"Subscribing to market data: {args.instruments}")
        gateway.subscribe_market_data(instrument_ids)

        # Keep alive and print incoming quotes
        print()
        print("Streaming market data (quotes will appear below)...")
        print("-" * 66)
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nShutting down CTP gateway...")
        try:
            gateway.disconnect()
        except Exception:
            pass
        gateway.stop()

    print("Gateway stopped.")


if __name__ == "__main__":
    main()
