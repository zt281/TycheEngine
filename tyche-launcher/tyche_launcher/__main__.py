"""Entry point for tyche-launcher."""

import argparse
import logging
import sys

from .config import load_launcher_config
from .launcher import Launcher


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TycheEngine Launcher")
    parser.add_argument(
        "--config",
        default="config/launcher-config.json",
        help="Path to launcher configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("tyche.launcher")

    # Load config
    try:
        config = load_launcher_config(args.config)
    except FileNotFoundError:
        logger.error(f"Config file not found: {args.config}")
        return 1
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return 1

    # Create and run launcher
    launcher = Launcher(config)

    try:
        launcher.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
    finally:
        launcher.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
