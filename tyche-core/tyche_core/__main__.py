"""Entry point for tyche-core service."""

import argparse
import logging
import signal
import sys
import os
from pathlib import Path

from .nexus import Nexus
from .bus import Bus
from .config import load_config_with_defaults


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def ensure_socket_dir(endpoint: str) -> None:
    """Create socket directory if needed."""
    if endpoint.startswith("ipc://"):
        path = endpoint[6:]  # Remove ipc://
        dir_path = os.path.dirname(path)
        if dir_path:
            Path(dir_path).mkdir(parents=True, exist_ok=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TycheEngine Core Service")
    parser.add_argument(
        "--config",
        default="config/core-config.json",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("tyche.core")

    # Load config
    try:
        config = load_config_with_defaults(args.config)
    except FileNotFoundError:
        logger.error(f"Config file not found: {args.config}")
        return 1

    # Ensure socket directories exist
    ensure_socket_dir(config["nexus"]["endpoint"])
    ensure_socket_dir(config["bus"]["xsub_endpoint"])
    ensure_socket_dir(config["bus"]["xpub_endpoint"])

    # Create services
    nexus = Nexus(
        endpoint=config["nexus"]["endpoint"],
        cpu_core=config["nexus"].get("cpu_core"),
        heartbeat_interval_ms=config["nexus"]["heartbeat_interval_ms"],
        heartbeat_timeout_ms=config["nexus"]["heartbeat_timeout_ms"],
    )

    bus = Bus(
        xsub_endpoint=config["bus"]["xsub_endpoint"],
        xpub_endpoint=config["bus"]["xpub_endpoint"],
        cpu_core=config["bus"].get("cpu_core"),
        high_water_mark=config["bus"].get("high_water_mark", 10000),
    )

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        nexus.stop()
        bus.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start services
    try:
        bus.start()
        nexus.start()
        logger.info("TycheEngine Core started")

        # Keep main thread alive
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        nexus.stop()
        bus.stop()
        logger.info("TycheEngine Core stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
