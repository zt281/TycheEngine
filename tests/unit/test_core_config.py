"""Unit tests for tyche_core.config module."""

import pytest
import json
import tempfile
import os


def test_load_config():
    from tyche_core.config import load_config

    config = {
        "nexus": {
            "endpoint": "ipc:///tmp/tyche/nexus.sock",
            "cpu_core": 0,
        },
        "bus": {
            "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
            "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
            "cpu_core": 1,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        fname = f.name

    try:
        loaded = load_config(fname)
        assert loaded["nexus"]["endpoint"] == "ipc:///tmp/tyche/nexus.sock"
        assert loaded["bus"]["cpu_core"] == 1
    finally:
        os.unlink(fname)


def test_load_config_missing_file():
    from tyche_core.config import load_config

    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.json")


def test_load_config_with_defaults():
    from tyche_core.config import load_config_with_defaults

    config = {"nexus": {}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        fname = f.name

    try:
        loaded = load_config_with_defaults(fname)
        assert loaded["nexus"]["endpoint"] == "ipc:///tmp/tyche/nexus.sock"
        assert loaded["bus"]["xsub_endpoint"] == "ipc:///tmp/tyche/bus_xsub.sock"
    finally:
        os.unlink(fname)


def test_load_config_defaults_hwm():
    from tyche_core.config import load_config_with_defaults

    config = {"bus": {}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        fname = f.name

    try:
        loaded = load_config_with_defaults(fname)
        assert loaded["bus"]["high_water_mark"] == 10000
    finally:
        os.unlink(fname)
