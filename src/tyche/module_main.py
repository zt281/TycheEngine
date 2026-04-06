#!/usr/bin/env python3
"""Standalone module process entry point."""

import argparse
import signal
import sys
from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def main():
    parser = argparse.ArgumentParser(description='Tyche Module - Example worker')
    parser.add_argument('--engine-host', default='127.0.0.1',
                        help='Engine host address')
    parser.add_argument('--engine-port', type=int, default=5555,
                        help='Engine registration port')
    parser.add_argument('--heartbeat-port', type=int, default=5559,
                        help='Engine heartbeat receive port (for sending heartbeats to)')
    parser.add_argument('--module-id', default=None,
                        help='Optional module ID (auto-generated if not provided)')

    args = parser.parse_args()

    module = ExampleModule(
        engine_endpoint=Endpoint(args.engine_host, args.engine_port),
        module_id=args.module_id,
        heartbeat_receive_endpoint=Endpoint(args.engine_host, args.heartbeat_port)
    )

    def shutdown(sig, frame):
        print("\nShutting down module...")
        module.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Starting module, connecting to engine at {args.engine_host}:{args.engine_port}")

    module.run()  # Blocking call


if __name__ == "__main__":
    main()
