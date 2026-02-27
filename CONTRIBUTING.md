# Contributing to agit

## Development Setup

### Prerequisites
- Rust 1.75+ (via rustup)
- Python 3.12+
- Node.js 18+
- Docker (optional, for integration tests)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/anthropics/agit.git
cd agit

# Rust
cargo build --workspace
cargo test --workspace

# Python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd crates/agit-python && maturin develop && cd ../..
pytest tests/

# TypeScript
cd ts-sdk && npm install && npm test && cd ..
```

## Branch Naming

- `feature/<description>` - New features
- `fix/<description>` - Bug fixes
- `docs/<description>` - Documentation
- `refactor/<description>` - Code refactoring

## Commit Message Format

```
<type>: <short description>

<optional body>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`

## Pull Request Process

1. Create a feature branch from `main`
2. Make changes with tests
3. Ensure all checks pass: `make test && make lint`
4. Submit PR with description of changes
5. Address review feedback
6. Squash-merge into `main`

## Testing Requirements

- All new features must include tests
- Rust: `cargo test --workspace`
- Python: `pytest tests/ --cov`
- TypeScript: `cd ts-sdk && npm test`

## Code Style

- **Rust**: `cargo fmt` + `cargo clippy -D warnings`
- **Python**: `ruff check` + `ruff format` + `mypy`
- **TypeScript**: `prettier` + `tsc --noEmit`
