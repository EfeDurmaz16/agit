# Stage 1: Build Rust core
FROM rust:1.83-bookworm AS rust-builder

WORKDIR /build
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY crates/ crates/

# Build the Python extension
RUN apt-get update && apt-get install -y python3-dev python3-pip && \
    pip3 install maturin --break-system-packages && \
    cd crates/agit-python && maturin build --release

# Stage 2: Python runtime
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install the built wheel
COPY --from=rust-builder /build/target/wheels/*.whl /tmp/
RUN pip install /tmp/*.whl && rm -rf /tmp/*.whl

# Install Python SDK
COPY pyproject.toml README.md ./
COPY python/ python/
RUN pip install -e ".[mcp,ui]"

# Copy examples
COPY examples/ examples/

EXPOSE 8501 8000

CMD ["agit", "--help"]
