# tests/unit/test_config.py
from pathlib import Path

_ROOT = Path(__file__).parents[2]

def test_engine_toml_loads():
    from tyche.core.config import EngineConfig
    cfg = EngineConfig.from_file(str(_ROOT / "config" / "engine.toml"))
    assert cfg.nexus.address == "tcp://127.0.0.1:5555"
    assert cfg.nexus.cpu_core == 0
    assert cfg.bus.xsub_address == "tcp://127.0.0.1:5556"

def test_module_config_loads():
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file(str(_ROOT / "config" / "modules" / "example_strategy.toml"))
    assert cfg.service_name == "strategy.example"
    assert cfg.cpu_core == 4
    assert "EQUITY.NYSE.AAPL.QUOTE" in cfg.subscriptions

def test_nexus_policy_loads():
    from tyche.core.config import NexusPolicy
    policy = NexusPolicy.from_file(str(_ROOT / "config" / "modules" / "nexus.toml"))
    assert policy.heartbeat_interval_ms == 1000
    assert policy.registration_max_retries == 20


def test_module_config_metrics_enabled_default():
    """metrics_enabled defaults to False when absent from TOML."""
    from tyche.core.config import ModuleConfig
    # Use _ROOT for an absolute path, matching the existing pattern in this file
    cfg = ModuleConfig.from_file(str(_ROOT / "config" / "modules" / "example_strategy.toml"))
    assert cfg.metrics_enabled is False


def test_module_config_metrics_enabled_true(tmp_path):
    """metrics_enabled=true is read from TOML correctly."""
    from tyche.core.config import ModuleConfig
    toml_content = b"""
[module]
service_name = "test.metrics"
metrics_enabled = true
"""
    p = tmp_path / "test_mod.toml"
    p.write_bytes(toml_content)
    cfg = ModuleConfig.from_file(str(p))
    assert cfg.metrics_enabled is True
    assert cfg.service_name == "test.metrics"
