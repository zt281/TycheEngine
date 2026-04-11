#!/usr/bin/env python3
"""Example: Start TycheEngine as a standalone process.

Usage:
    python examples/run_engine.py

Then in another terminal:
    python examples/run_module.py
"""

import sys
import os
import logging

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tyche.engine import TycheEngine
from tyche.types import Endpoint

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s')


def main():
    print("=" * 60)
    print("Tyche Engine - Standalone Process Example")
    print("=" * 60)
    print()

    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5558),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559),
        admin_endpoint="tcp://127.0.0.1:5560"
    )

    print("Engine configuration:")
    print(f"  Registration: tcp://127.0.0.1:5555")
    print(f"  Events: tcp://127.0.0.1:5556")
    print(f"  Heartbeat (out): tcp://127.0.0.1:5558")
    print(f"  Heartbeat (in): tcp://127.0.0.1:5559")
    print(f"  Admin: tcp://127.0.0.1:5560")
    print()
    print("Press Ctrl+C to stop")
    print()

    try:
        engine.run()  # Blocks until interrupted
    except KeyboardInterrupt:
        print("\nShutting down...")
        engine.stop()

    print("Engine stopped.")


if __name__ == "__main__":
    main()
