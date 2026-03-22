# tests/unit/test_cli_scaffold.py
import importlib.util
import py_compile
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]
from io import StringIO
from unittest import mock


def test_generated_strategy_compiles(tmp_path, monkeypatch):
    """Generated .py file is syntactically valid (passes py_compile)."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "alpha_strat"]):
        main()
    strategy_file = tmp_path / "strategies" / "alpha_strat.py"
    assert strategy_file.exists(), f"Expected {strategy_file} to be created"
    py_compile.compile(str(strategy_file), doraise=True)


def test_generated_strategy_importable(tmp_path, monkeypatch):
    """Generated .py imports cleanly and contains the correct PascalCase class."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "my_strat"]):
        main()
    strategy_file = tmp_path / "strategies" / "my_strat.py"
    spec = importlib.util.spec_from_file_location("my_strat", str(strategy_file))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "tyche_core", mock.MagicMock())
    spec.loader.exec_module(mod)
    assert hasattr(mod, "MyStrat"), "Expected class MyStrat in generated module"


def test_generated_config_fields(tmp_path, monkeypatch):
    """Generated .toml contains all required fields with correct values."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "beta_strat"]):
        main()
    config_file = tmp_path / "config" / "modules" / "beta_strat.toml"
    assert config_file.exists(), f"Expected {config_file} to be created"
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    m = data["module"]
    assert m["service_name"] == "beta_strat"
    assert m["nexus_address"] == "tcp://localhost:5555"
    assert m["bus_xsub"] == "tcp://localhost:5556"
    assert m["bus_xpub"] == "tcp://localhost:5557"
    assert m["metrics_enabled"] == False


def test_pascal_case_conversion():
    """_to_pascal_case converts snake_case names to PascalCase correctly."""
    from tyche.cli.__main__ import _to_pascal_case
    assert _to_pascal_case("alpha") == "Alpha"
    assert _to_pascal_case("my_strat") == "MyStrat"
    assert _to_pascal_case("my_strategy_name") == "MyStrategyName"
    assert _to_pascal_case("a_b_c") == "ABC"


def test_invalid_name_exits_with_error(tmp_path, monkeypatch, capsys):
    """Invalid name prints error to stderr and exits with code 1."""
    import pytest
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "Bad-Name"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: name must match [a-z][a-z0-9_]*" in captured.err
