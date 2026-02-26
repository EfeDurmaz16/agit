# =============================================================================
# Stage 1: Rust builder – compile agit-core and agit-python extension
# =============================================================================
FROM rust:1.83-bookworm AS rust-builder

WORKDIR /build

# Cache dependency compilation separately from source changes
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY crates/ crates/

# Install maturin and Python dev headers needed to build the PyO3 extension
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3-dev \
        python3-pip \
        libclang-dev \
        pkg-config \
    && pip3 install "maturin>=1.4,<2" --break-system-packages \
    && rm -rf /var/lib/apt/lists/*

# Build the Python wheel for agit-python (release profile)
RUN cd crates/agit-python && \
    maturin build --release --strip --out /build/target/wheels

# =============================================================================
# Stage 2: Python runtime – minimal image with agit installed
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="agit" \
      org.opencontainers.image.description="Git-like version control for AI agents" \
      org.opencontainers.image.source="https://github.com/example/agit" \
      org.opencontainers.image.version="0.1.0"

WORKDIR /app

# Install OS-level runtime deps (SQLite is bundled in Python's stdlib)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libssl3 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the native Rust wheel first so the pure-Python package can detect it
COPY --from=rust-builder /build/target/wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

# Install the Python SDK and optional extras
COPY pyproject.toml README.md ./
COPY python/ python/
RUN pip install --no-cache-dir -e ".[mcp,ui]"

# Copy examples (useful for interactive container sessions)
COPY examples/ examples/

# Non-root user for security
RUN useradd --create-home --shell /bin/bash agit
USER agit

# MCP server port (8000) and Streamlit UI port (8501)
EXPOSE 8000 8501

# Default: show CLI help. Override in docker-compose for specific services.
CMD ["agit", "--help"]
