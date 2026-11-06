#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS="$PWD/.cache/ollama/models"
export OLLAMA_NO_CLOUD=1
export OLLAMA_MAX_LOADED_MODELS=1
exec ollama serve
