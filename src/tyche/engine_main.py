#!/usr/bin/env python3
"""Standalone TycheEngine process entry point."""

import argparse
import signal
import sys
from tyche.engine import TycheEngine
from tyche.types import Endpoint


def main():
    parser = argparse.ArgumentParser(description='Tyche Engine - Central broker')
    parser.add_argument('--registration-port', type=int, default=5555,
                        help='Port for module registration (ROUTER)')
    parser.add_argument('--event-port', type=int, default=5556,
                        help='Port for event broadcasting (XPUB/XSUB)')
    parser.add_argument('--heartbeat-port', type=int, default=5558,
                        help='Port for heartbeat (PUB)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Host to bind to')

    args = parser.parse_args()

    engine = TycheEngine(
        registration_endpoint=Endpoint(args.host, args.registration_port),
        event_endpoint=Endpoint(args.host, args.event_port),
        heartbeat_endpoint=Endpoint(args.host, args.heartbeat_port)
    )

    def shutdown(sig, frame):
        print("\nShutting down engine...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Starting TycheEngine on {args.host}")
    print(f"  Registration: port {args.registration_port}")
    print(f"  Events: port {args.event_port}")
    print(f"  Heartbeat: port {args.heartbeat_port}")

    engine.run()  # Blocking call


if __name__ == "__main__":
    main()
