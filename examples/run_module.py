#!/usr/bin/env python3
"""Example: Start Tyche Module as a standalone process.

Usage:
    # First start the engine in another terminal:
    python examples/run_engine.py

    # Then start this module:
    python examples/run_module.py
"""

import sys
import os

# Add src to path for examples
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def main():
    print("=" * 60)
    print("Tyche Module - Standalone Process Example")
    print("=" * 60)
    print()

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559)
    )

    print(f"Module ID: {module.module_id}")
    print("Connecting to engine at: tcp://127.0.0.1:5555")
    print("Sending heartbeats to: tcp://127.0.0.1:5559")
    print()
    print("Press Ctrl+C to stop")
    print()

    try:
        module.run()  # Blocks until interrupted
    except KeyboardInterrupt:
        print("\nShutting down...")
        module.stop()

    print("Module stopped.")


if __name__ == "__main__":
    main()
