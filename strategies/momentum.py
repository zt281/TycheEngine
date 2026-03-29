#!/usr/bin/env python3
"""Momentum strategy example."""

import argparse
import logging

from tyche_client import Module, Tick, Quote, Order


class MomentumStrategy(Module):
    """Simple momentum strategy using moving average crossover."""

    service_name = "strategy.momentum"
    service_version = "1.0.0"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fast_ma = 0.0
        self.slow_ma = 0.0
        self.position = 0
        self._order_id_counter = 0

    def on_init(self):
        """Called after registration."""
        # Subscribe to market data
        self.subscribe("EQUITY.NYSE.*.Tick")
        self.subscribe("EQUITY.NYSE.*.Quote")

        # Load strategy config
        cfg = self._config.get("strategy", {})
        self.lookback = cfg.get("lookback_period", 20)
        self.threshold = cfg.get("threshold", 0.001)

        self._logger.info(f"Momentum strategy initialized: lookback={self.lookback}")

    def on_start(self):
        """Called on START command."""
        self._logger.info("Strategy started")

    def on_stop(self):
        """Called on STOP command."""
        self._logger.info("Strategy stopped")

    def on_tick(self, tick: Tick):
        """Process tick data."""
        # Update moving averages using EMA
        alpha_fast = 2.0 / (self.lookback / 2 + 1)
        alpha_slow = 2.0 / (self.lookback + 1)

        self.fast_ma = alpha_fast * tick.price + (1 - alpha_fast) * self.fast_ma
        self.slow_ma = alpha_slow * tick.price + (1 - alpha_slow) * self.slow_ma

        # Skip until we have valid averages
        if self.fast_ma == 0 or self.slow_ma == 0:
            return

        # Trading logic
        if self.fast_ma > self.slow_ma * (1 + self.threshold) and self.position <= 0:
            # Buy signal
            self._place_order(tick, "buy", 100.0)
            self.position = 100

        elif self.fast_ma < self.slow_ma * (1 - self.threshold) and self.position >= 0:
            # Sell signal
            self._place_order(tick, "sell", 100.0)
            self.position = -100

    def on_quote(self, quote: Quote):
        """Process quote data."""
        # Can use quotes for more sophisticated pricing
        pass

    def _place_order(self, tick: Tick, side: str, qty: float):
        """Place an order."""
        self._order_id_counter += 1
        order = Order(
            instrument_id=tick.instrument_id,
            client_order_id=self._order_id_counter,
            price=tick.price,
            qty=qty,
            side=side,
            order_type="limit",
            tif="GTC",
            timestamp_ns=tick.timestamp_ns,
        )
        self.send_order(order)
        self._logger.info(f"Placed {side} order for {qty} @ {tick.price}")


def main():
    parser = argparse.ArgumentParser(description="Momentum Strategy")
    parser.add_argument("--nexus", required=True, help="Nexus IPC endpoint")
    parser.add_argument("--bus-xsub", required=True, help="Bus XSUB IPC endpoint")
    parser.add_argument("--bus-xpub", required=True, help="Bus XPUB IPC endpoint")
    parser.add_argument("--config", default="config.json", help="Module config file")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    strategy = MomentumStrategy(
        nexus_endpoint=args.nexus,
        bus_xsub_endpoint=args.bus_xsub,
        bus_xpub_endpoint=args.bus_xpub,
        config_path=args.config,
    )
    strategy.run()


if __name__ == "__main__":
    main()
