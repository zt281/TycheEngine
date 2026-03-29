.PHONY: all build install test lint clean

all: build

build: build-core build-client

build-core:
	pip install -e tyche-core/

build-client:
	pip install -e tyche-client/

install: build

test: test-unit test-integration

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

lint:
	ruff check tyche-core/ tyche-client/ tyche-launcher/ tests/ strategies/

lint-fix:
	ruff check --fix tyche-core/ tyche-client/ tyche-launcher/ tests/ strategies/

format:
	ruff format tyche-core/ tyche-client/ tyche-launcher/ tests/ strategies/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf tyche-core/*.egg-info tyche-client/*.egg-info tyche-launcher/*.egg-info 2>/dev/null || true
	rm -rf .pytest_cache

run-core:
	python -m tyche_core --config config/core-config.json

run-momentum:
	python strategies/momentum.py \
		--nexus ipc:///tmp/tyche/nexus.sock \
		--bus-xsub ipc:///tmp/tyche/bus_xsub.sock \
		--bus-xpub ipc:///tmp/tyche/bus_xpub.sock \
		--config config/modules/momentum-config.json
