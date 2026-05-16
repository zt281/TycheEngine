import logging
import signal
import sys

from src.tyche.engine import TycheEngine
from tyche.types import Endpoint


def setup_logging() -> None:
    """Configure root logger for console output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def start_engine() -> TycheEngine:
    logger = logging.getLogger(__name__)
    logger.info("Creating TycheEngine instance...")
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5559),
        admin_endpoint="tcp://127.0.0.1:5558",
    )
    logger.info("TycheEngine instance created.")
    return engine


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    engine = start_engine()

    def _signal_handler(signum: int, _frame) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down...", sig_name)
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Starting TycheEngine...")
    try:
        engine.run()
    except Exception as e:
        logger.exception("TycheEngine crashed: %s", e)
        raise
    finally:
        logger.info("TycheEngine stopped.")


if __name__ == "__main__":
    main()
