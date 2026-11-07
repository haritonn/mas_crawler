FROM node:24-bookworm-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        pkg-config \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh \
        && sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain stable \
        && rm /tmp/rustup-init.sh

ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY core ./core/
COPY templates/search-service ./templates/search-service/

RUN uv sync --locked --no-dev --no-editable

RUN cargo build --locked --release \
    --manifest-path core/Cargo.toml \
    --bin mas-crawler-core


FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libssl3 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/core/target/release/mas-crawler-core /usr/local/bin/mas-crawler-core
COPY --from=frontend-builder /frontend/dist /app/frontend/dist
COPY config.toml ./config.toml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 10001 app \
    && mkdir /data \
    && chown app:app /data

USER app
EXPOSE 8000
CMD ["python", "-c", "from pathlib import Path; import uvicorn; from mas_crawler.web.app import create_app; uvicorn.run(create_app(runs_dir=Path('/data/runs'), config=Path('/app/config.toml'), static_dir=Path('/app/frontend/dist')), host='0.0.0.0', port=8000)"]
