#!/usr/bin/env python3
"""Example: Run the Simulated Gateway as a standalone process.

This demonstrates running a gateway module independently.
Start the engine first, then run this script.

Usage:
    # Terminal 1: Start engine
    python examples/run_engine.py

    # Terminal 2: Start gateway
    python examples/run_gateway.py

    # Terminal 3: Start strategy
    python examples/run_strategy.py
"""

import logging
import os
import sys
import time
from decimal import Decimal

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from modules.trading.gateway.simulated import SimulatedGateway
from tyche.types import Endpoint

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)


def main() -> None:
    print("=" * 60)
    print("  TycheEngine - Simulated Gateway Module")
    print("=" * 60)
    print()

    INSTRUMENTS = [
        "BTCUSDT.simulated.crypto",
        "ETHUSDT.simulated.crypto",
        "SOLUSDT.simulated.crypto",
    ]

    gateway = SimulatedGateway(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559),
        instruments=INSTRUMENTS,
        tick_interval=0.5,
        base_prices={
            "BTCUSDT.simulated.crypto": Decimal("65000.00"),
            "ETHUSDT.simulated.crypto": Decimal("3200.00"),
            "SOLUSDT.simulated.crypto": Decimal("145.00"),
        },
        fill_latency=0.05,
        fill_probability=0.98,
    )

    print(f"Gateway ID: {gateway.module_id}")
    print(f"Venue: {gateway.venue_name}")
    print(f"Instruments: {', '.join(INSTRUMENTS)}")
    print("Tick interval: 0.5s")
    print()
    print("Connecting to engine at tcp://127.0.0.1:5555")
    print("Press Ctrl+C to stop")
    print()

    try:
        gateway.start_nonblocking()
        time.sleep(1)

        # Start generating market data
        print("Starting market data generation...")
        gateway.start_market_data()

        # Keep alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down gateway...")
        gateway.stop()

    print("Gateway stopped.")


if __name__ == "__main__":
    main()
