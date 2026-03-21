.PHONY: build test lint clean

build:
	maturin develop --release

test: build
	cargo test --manifest-path tyche-core/Cargo.toml
	pytest tests/ -v

lint:
	cargo clippy --manifest-path tyche-core/Cargo.toml -- -D warnings
	ruff check tyche/ tests/

clean:
	cargo clean
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
