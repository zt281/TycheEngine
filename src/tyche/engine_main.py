"""TycheEngine standalone entry point.

Usage:
    python -m src.tyche.engine_main --registration-port 5555

Or:
    python src/tyche/engine_main.py --registration-port 5555
"""

import argparse
import logging
import signal
import threading
from pathlib import Path

from src.tyche.engine import TycheEngine
from src.tyche.types import Endpoint

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start TycheEngine")
    parser.add_argument(
        "--registration-port",
        type=int,
        default=5555,
        help="Registration port (default: 5555)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Data directory (default: data)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    args = parser.parse_args()

    # Logging setup
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure data directory exists
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Port layout (matches src/tyche/types.py):
    #   Registration ROUTER:  base_port + 0  (5555)
    #   Event XPUB:           base_port + 1  (5556)
    #   Event XSUB:           base_port + 2  (5557)
    #   Admin ROUTER:         base_port + 3  (5558)
    #   Heartbeat PUB:        base_port + 4  (5559)
    #   Heartbeat Recv:       base_port + 5  (5560)
    #   Job ROUTER:           base_port + 9  (5564)
    base_port = args.registration_port
    host = args.host

    engine = TycheEngine(
        registration_endpoint=Endpoint(host, base_port),
        event_endpoint=Endpoint(host, base_port + 1),
        heartbeat_endpoint=Endpoint(host, base_port + 4),
        data_dir=str(data_dir),
    )

    stop_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down TycheEngine...", sig_name)
        stop_event.set()
        engine.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Starting TycheEngine on %s:%d...", host, base_port)
    engine.start()
    logger.info("TycheEngine stopped.")


if __name__ == "__main__":
    main()
