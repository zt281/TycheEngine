#!/usr/bin/env python3
"""Example: Run trading infrastructure services (Risk + OMS + Portfolio).

These services handle order routing, risk checking, and position tracking.
They sit between the strategy and gateway modules.

Usage:
    # Terminal 1: Start engine
    python examples/run_engine.py

    # Terminal 2: Start this (trading services)
    python examples/run_trading_services.py

    # Terminal 3: Start gateway
    python examples/run_gateway.py

    # Terminal 4: Start strategy
    python examples/run_strategy.py
"""

import sys
import os
import logging
import time
from decimal import Decimal

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tyche.types import Endpoint
from tyche.trading.oms.module import OMSModule
from tyche.trading.risk.module import RiskModule
from tyche.trading.risk.rules import (
    MaxDailyLossRule,
    MaxOrderValueRule,
    MaxPositionSizeRule,
    RateLimitRule,
)
from tyche.trading.portfolio.module import PortfolioModule
from tyche.trading.data.recorder import DataRecorderModule

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)


def main() -> None:
    print("=" * 60)
    print("  TycheEngine - Trading Services (Risk + OMS + Portfolio)")
    print("=" * 60)
    print()

    INSTRUMENTS = [
        "BTCUSDT.simulated.crypto",
        "ETHUSDT.simulated.crypto",
        "SOLUSDT.simulated.crypto",
    ]

    engine_endpoint = Endpoint("127.0.0.1", 5555)
    hb_recv_endpoint = Endpoint("127.0.0.1", 5559)

    # --- Risk Module ---
    print("[1/4] Starting Risk Module...")
    risk = RiskModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        rules=[
            MaxPositionSizeRule(max_size=Decimal("10.0")),
            MaxOrderValueRule(max_value=Decimal("100000")),
            MaxDailyLossRule(max_loss=Decimal("5000")),
            RateLimitRule(min_interval_seconds=0.1, max_orders_per_minute=120),
        ],
    )
    risk.start_nonblocking()
    time.sleep(0.5)
    print(f"  Risk ID: {risk.module_id}")

    # --- OMS ---
    print("[2/4] Starting OMS Module...")
    oms = OMSModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
    )
    oms.start_nonblocking()
    time.sleep(0.5)
    print(f"  OMS ID: {oms.module_id}")

    # --- Portfolio ---
    print("[3/4] Starting Portfolio Module...")
    portfolio = PortfolioModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
    )
    portfolio.subscribe_quotes(INSTRUMENTS)
    portfolio.start_nonblocking()
    time.sleep(0.5)
    print(f"  Portfolio ID: {portfolio.module_id}")

    # --- Data Recorder ---
    print("[4/4] Starting Data Recorder...")
    recorder = DataRecorderModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        data_dir="./data/recorded",
        instrument_ids=INSTRUMENTS,
    )
    recorder.start_nonblocking()
    time.sleep(0.5)
    print(f"  Recorder ID: {recorder.module_id}")

    print()
    print("All trading services running. Press Ctrl+C to stop.")
    print()

    try:
        while True:
            time.sleep(10)
            print(f"\n--- Service Stats ---")
            print(f"  OMS: {oms.order_store.active_count} active / {oms.order_store.total_count} total")
            print(f"  Portfolio PnL: realized={portfolio.total_realized_pnl:.4f}, unrealized={portfolio.total_unrealized_pnl:.4f}")
            print(f"  Recorder: {recorder.event_count} events")
    except KeyboardInterrupt:
        print("\nShutting down services...")

    recorder.stop()
    portfolio.stop()
    oms.stop()
    risk.stop()

    print("All services stopped.")


if __name__ == "__main__":
    main()
