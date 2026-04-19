#!/usr/bin/env python3
"""Example: Run a complete multi-asset trading system in a single process.

This demonstrates the full TycheEngine trading pipeline:
    Engine -> Gateway (simulated) -> Strategy (EMA cross) -> Risk -> OMS -> Portfolio

All modules run as threads within the same engine process for simplicity.
In production, each module would run as a separate process.

Usage:
    python examples/run_trading_system.py

Press Ctrl+C to stop.
"""

import logging
import os
import sys
import time
from decimal import Decimal

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from modules.trading.gateway.simulated import SimulatedGateway
from modules.trading.oms.module import OMSModule
from modules.trading.portfolio.module import PortfolioModule
from modules.trading.risk.module import RiskModule
from modules.trading.risk.rules import MaxDailyLossRule, MaxOrderValueRule, MaxPositionSizeRule
from modules.trading.store.recorder import DataRecorderModule
from modules.trading.strategy.example_ma_cross import MovingAverageCrossStrategy
from tyche.engine import TycheEngine
from tyche.types import Endpoint

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)

# Silence overly chatty loggers
logging.getLogger("tyche.module").setLevel(logging.WARNING)
logging.getLogger("tyche.engine").setLevel(logging.WARNING)


def main() -> None:
    print("=" * 70)
    print("  TycheEngine - Multi-Asset Trading System (Simulated)")
    print("=" * 70)
    print()

    # --- Configuration ---
    INSTRUMENTS = [
        "BTCUSDT.simulated.crypto",
        "ETHUSDT.simulated.crypto",
    ]
    ENGINE_HOST = "127.0.0.1"
    REG_PORT = 5555
    HB_RECV_PORT = 5559

    engine_endpoint = Endpoint(ENGINE_HOST, REG_PORT)
    hb_recv_endpoint = Endpoint(ENGINE_HOST, HB_RECV_PORT)

    # --- Start Engine ---
    print("[1/7] Starting TycheEngine...")
    engine = TycheEngine(
        registration_endpoint=Endpoint(ENGINE_HOST, REG_PORT),
        event_endpoint=Endpoint(ENGINE_HOST, 5556),
        heartbeat_endpoint=Endpoint(ENGINE_HOST, 5558),
        heartbeat_receive_endpoint=Endpoint(ENGINE_HOST, HB_RECV_PORT),
        admin_endpoint=f"tcp://{ENGINE_HOST}:5560",
    )
    engine.start_nonblocking()
    time.sleep(0.5)

    # --- Start Risk Module ---
    print("[2/7] Starting Risk Module...")
    risk = RiskModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        rules=[
            MaxPositionSizeRule(max_size=Decimal("10.0")),
            MaxOrderValueRule(max_value=Decimal("100000")),
            MaxDailyLossRule(max_loss=Decimal("5000")),
        ],
    )
    risk.start_nonblocking()
    time.sleep(0.3)

    # --- Start OMS ---
    print("[3/7] Starting Order Management System...")
    oms = OMSModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
    )
    oms.start_nonblocking()
    time.sleep(0.3)

    # --- Start Portfolio ---
    print("[4/7] Starting Portfolio Module...")
    portfolio = PortfolioModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
    )
    portfolio.subscribe_quotes(INSTRUMENTS)
    portfolio.start_nonblocking()
    time.sleep(0.3)

    # --- Start Data Recorder ---
    print("[5/7] Starting Data Recorder...")
    recorder = DataRecorderModule(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        data_dir="./data/recorded",
        instrument_ids=INSTRUMENTS,
    )
    recorder.start_nonblocking()
    time.sleep(0.3)

    # --- Start Simulated Gateway ---
    print("[6/7] Starting Simulated Gateway...")
    gateway = SimulatedGateway(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        instruments=INSTRUMENTS,
        tick_interval=0.3,  # Generate quotes every 300ms
        base_prices={
            "BTCUSDT.simulated.crypto": Decimal("65000.00"),
            "ETHUSDT.simulated.crypto": Decimal("3200.00"),
        },
    )
    gateway.start_nonblocking()
    time.sleep(0.3)
    gateway.start_market_data()

    # --- Start Strategy ---
    print("[7/7] Starting EMA Crossover Strategy...")
    strategy = MovingAverageCrossStrategy(
        engine_endpoint=engine_endpoint,
        heartbeat_receive_endpoint=hb_recv_endpoint,
        instruments=INSTRUMENTS,
        fast_period=5,
        slow_period=15,
        order_quantity=Decimal("0.1"),
    )
    strategy.start_nonblocking()
    time.sleep(0.5)

    print()
    print("=" * 70)
    print("  All modules started. Trading system is LIVE (simulated).")
    print("  Watching: " + ", ".join(INSTRUMENTS))
    print("  Strategy: EMA Crossover (fast=5, slow=15)")
    print("  Risk: max_pos=10, max_order_value=100k, max_daily_loss=5k")
    print("=" * 70)
    print()
    print("Press Ctrl+C to stop...")
    print()

    # --- Main loop: print periodic stats ---
    try:
        tick = 0
        while True:
            time.sleep(5)
            tick += 1

            # Print stats every 5 seconds
            print(f"\n--- Stats (t={tick * 5}s) ---")
            print(f"  OMS: {oms.order_store.active_count} active / {oms.order_store.total_count} total orders")
            print(f"  Portfolio: realized={portfolio.total_realized_pnl:.2f}, unrealized={portfolio.total_unrealized_pnl:.2f}")
            print(f"  Recorder: {recorder.event_count} events recorded")

            for iid in INSTRUMENTS:
                pos = portfolio.get_position(iid)
                if pos.quantity > 0:
                    print(f"  Position {iid}: {pos.side.name} {pos.quantity} @ {pos.avg_entry_price:.2f} (pnl={pos.net_pnl:.2f})")

    except KeyboardInterrupt:
        print("\n\nShutting down trading system...")

    # --- Graceful shutdown (reverse order) ---
    strategy.stop()
    gateway.stop()
    recorder.stop()
    portfolio.stop()
    oms.stop()
    risk.stop()
    engine.stop()

    print("All modules stopped. Goodbye!")


if __name__ == "__main__":
    main()
