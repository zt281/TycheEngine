# Unit Test Coverage Plan v1

## Goal
Add comprehensive unit tests for all trading pipeline modules and one end-to-end integration test.

## Modules to Cover

### Wave 1: Core Trading Logic (Unit Tests)
| File | Module | Key Behaviors to Test |
|------|--------|----------------------|
| `tests/unit/test_order_store.py` | `OrderStore` | add, get, update_status transitions, apply_fill, active orders, thread safety |
| `tests/unit/test_oms_module.py` | `OMSModule` | order approved routing, fill handling, cancel routing, venue extraction |
| `tests/unit/test_portfolio_module.py` | `PortfolioModule` | fill -> position update, quote -> mark-to-market, P&L calculation |
| `tests/unit/test_risk_rules.py` | `RiskRule` + `RiskRuleEngine` | all 4 rules pass/fail, engine evaluate + is_approved, context updates |
| `tests/unit/test_strategy_context.py` | `StrategyContext` + `StrategyModule` | submit_order builds correct Order, cancel_order, quote dispatch, position dispatch |
| `tests/unit/test_simulated_gateway.py` | `SimulatedGateway` | connect/disconnect, submit_order fill/reject, cancel_order, query_account, price generation |
| `tests/unit/test_data_recorder.py` | `DataRecorderModule` | event recording, file creation, event type inference, subscribe_instrument |

### Wave 2: End-to-End Integration
| File | Flow | Verification |
|------|------|-------------|
| `tests/integration/test_trading_pipeline.py` | StrategyContext.submit_order -> RiskModule -> OMSModule -> SimulatedGateway -> PortfolioModule | Each stage produces correct events; final position matches fill |

## Testing Approach

- Mock ZMQ by mocking `tyche.module.zmq.Context` or using `patch.object(module, "send_event")`
- Mock time where needed with `patch("time.time", return_value=...)`
- Use temporary directories for file I/O tests (`tmp_path` fixture)
- Do NOT add `__init__.py` to `tests/` subdirectories
- Target: each test file < 300 lines

## TDD Steps

For each test file:
1. **RED**: Write tests first, run `pytest`, confirm failures are expected (missing methods/handler not found)
2. **GREEN**: Ensure all tests pass
3. Record pass output in task log
