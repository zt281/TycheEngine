"""TycheEngine Trading Domain - Multi-asset real-time automated trading framework.

Key components:
- models: Pure data classes (Order, Quote, Position, etc.)
- events: Event name constants for the trading event bus
- gateway: Abstract base for exchange connectivity
- strategy: Strategy framework with context for order management
- oms: Order Management System with state machine
- risk: Pre-trade risk rule engine
- portfolio: Position and P&L tracking
- clock: Time abstraction (live + simulated)
- data: Recording and replay for backtesting
"""
