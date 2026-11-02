FROM rust:1-bookworm AS rust-toolchain

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH \
    UV_PYTHON_DOWNLOADS=0 \
    CARGO_BUILD_JOBS=2
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY native/ native/
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable
COPY search.toml ./
COPY data/ data/
RUN uv run --no-sync search-service build

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 search
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/search.toml /app/search.toml
COPY --from=builder /app/data /app/data
COPY --from=builder /app/indexes /app/indexes
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER search
EXPOSE 8000
CMD ["search-service", "serve", "--host", "0.0.0.0"]
