#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.cache/python"
exec uv run --frozen uvicorn forge.app:app --host 127.0.0.1 --port 8000 --no-access-log
