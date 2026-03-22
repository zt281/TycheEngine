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

def test_module_config_address_defaults():
    """When address fields are absent from TOML, ModuleConfig uses localhost defaults."""
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file(str(_ROOT / "config" / "modules" / "example_strategy.toml"))
    assert cfg.nexus_address == "tcp://localhost:5555"
    assert cfg.bus_xsub == "tcp://localhost:5556"
    assert cfg.bus_xpub == "tcp://localhost:5557"

def test_module_config_address_from_toml(tmp_path):
    """When address fields are present in TOML, ModuleConfig reads them."""
    toml_content = """
[module]
service_name = "test.svc"
nexus_address = "tcp://10.0.0.1:5555"
bus_xsub = "tcp://10.0.0.1:5556"
bus_xpub = "tcp://10.0.0.1:5557"
"""
    cfg_path = tmp_path / "m.toml"
    cfg_path.write_text(toml_content)
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file(str(cfg_path))
    assert cfg.nexus_address == "tcp://10.0.0.1:5555"
    assert cfg.bus_xsub == "tcp://10.0.0.1:5556"
    assert cfg.bus_xpub == "tcp://10.0.0.1:5557"
