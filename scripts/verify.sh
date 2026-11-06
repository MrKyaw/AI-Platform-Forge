#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.cache/python"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
mkdir -p .cache
uv run --frozen ruff format --check forge scripts tests
uv run --frozen ruff check forge scripts tests
uv run --frozen mypy forge scripts
node --check forge/static/app.js
uv run --frozen pytest --cov --cov-report=term --cov-report=json:.cache/coverage.json
uv run --frozen python -m scripts.check_docs
uv run --frozen python -m compileall -q forge scripts
uv run --frozen pip-audit --format json --output .cache/dependency-audit.json
uv run --frozen python -m scripts.smoke
uv run --frozen python -m scripts.evaluate
