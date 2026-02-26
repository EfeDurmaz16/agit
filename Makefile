.PHONY: build test lint clean dev format

# Build all targets
build: build-rust build-python build-ts

build-rust:
	cargo build --workspace

build-python: build-rust
	cd crates/agit-python && maturin develop

build-ts: build-rust
	cd crates/agit-node && npm run build

# Run all tests
test: test-rust test-python test-ts

test-rust:
	cargo test --workspace

test-python:
	pytest tests/ -v

test-ts:
	cd ts-sdk && npm test

# Lint all targets
lint: lint-rust lint-python

lint-rust:
	cargo clippy --all-targets -- -D warnings
	cargo fmt --check

lint-python:
	ruff check python/ tests/
	mypy python/agit/

# Format all targets
format:
	cargo fmt
	ruff format python/ tests/

# Development setup
dev:
	pip install -e ".[dev]"
	cd crates/agit-python && maturin develop
	cd ts-sdk && npm install

# Clean all build artifacts
clean:
	cargo clean
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf ts-sdk/dist/ ts-sdk/node_modules/
