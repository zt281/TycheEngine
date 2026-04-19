#!/usr/bin/env python3
"""Example: Run the EMA Crossover Strategy as a standalone process.

Requires the engine, gateway, risk, OMS, and portfolio modules to be running.

Usage:
    # Terminal 1: Start engine
    python examples/run_engine.py

    # Terminal 2: Start gateway
    python examples/run_gateway.py

    # Terminal 3: Start supporting modules (risk + OMS + portfolio)
    python examples/run_trading_services.py

    # Terminal 4: Start this strategy
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
from tyche.trading.strategy.example_ma_cross import MovingAverageCrossStrategy

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)


def main() -> None:
    print("=" * 60)
    print("  TycheEngine - EMA Crossover Strategy Module")
    print("=" * 60)
    print()

    INSTRUMENTS = [
        "BTCUSDT.simulated.crypto",
        "ETHUSDT.simulated.crypto",
    ]

    strategy = MovingAverageCrossStrategy(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559),
        instruments=INSTRUMENTS,
        fast_period=5,
        slow_period=15,
        order_quantity=Decimal("0.1"),
    )

    print(f"Strategy ID: {strategy.module_id}")
    print(f"Instruments: {', '.join(INSTRUMENTS)}")
    print(f"EMA periods: fast=5, slow=15")
    print(f"Order size: 0.1")
    print()
    print("Connecting to engine at tcp://127.0.0.1:5555")
    print("Press Ctrl+C to stop")
    print()

    try:
        strategy.start_nonblocking()

        # Keep alive and print stats
        while True:
            time.sleep(10)
            stats = strategy.get_stats()
            print(f"\n--- Strategy Stats ---")
            print(f"  Tick counts: {stats['tick_counts']}")
            print(f"  EMAs: {stats['current_emas']}")
    except KeyboardInterrupt:
        print("\nShutting down strategy...")
        strategy.stop()

    print("Strategy stopped.")


if __name__ == "__main__":
    main()
