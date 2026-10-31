set positional-arguments

# TOML-конфигурация Python-команд; переопределяется через just --set app_config FILE.
export app_config := "config.toml"

# Показать доступные команды.
[private]
default:
    @just --list

# Установить зависимости и собрать Python-пакет с Rust-расширением.
setup:
    uv sync --locked

# Установить frontend-зависимости и собрать интерфейс.
ui-build:
    npm --prefix frontend ci
    npm --prefix frontend run build

# Открыть локальный веб-сервер: сначала выполните just ui-build.
ui *args:
    uv run --locked mas-crawler-web --config "$app_config" "$@"

# Frontend с hot reload; API запускается отдельно через just ui.
ui-dev:
    npm --prefix frontend run dev

# Отформатировать Python- и Rust-код (изменяет файлы).
fmt:
    uv run --locked ruff format src
    cargo fmt --manifest-path core/Cargo.toml

# Последовательно проверить линтер, форматирование и Rust-тесты.
check:
    uv run --locked ruff check src
    uv run --locked ruff format --check src
    cargo fmt --manifest-path core/Cargo.toml -- --check
    cargo test --locked --manifest-path core/Cargo.toml

# Подготовить план обхода через LLM: URL --goal GOAL [--output FILE].
analyze +args:
    uv run --locked mas-crawler --config "$app_config" analyze "$@"

# Собрать корпус и индекс: URL --goal GOAL либо --plan FILE; нужен --run-dir DIR.
build +args:
    uv run --locked mas-crawler --config "$app_config" build "$@"

# Собрать корпус, индекс и пакет для разметки из URL + goal.
dataset +args:
    uv run --locked mas-crawler --config "$app_config" dataset "$@"

# Выдать CSV для разметки или принять оценки: prepare|accept [параметры].
benchmark +args:
    uv run --locked mas-crawler --config "$app_config" benchmark "$@"

# Найти документы: --index DIR --query TEXT [--top-k N] [--config JSON].
search +args:
    cargo run --locked --manifest-path core/Cargo.toml -- search "$@"

# Сравнить выдачи конфигураций: --index DIR --plan JSON [--parallelism N].
experiment +args:
    cargo run --locked --manifest-path core/Cargo.toml -- experiment "$@"
