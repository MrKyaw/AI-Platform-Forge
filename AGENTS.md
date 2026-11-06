# Working on AI Platform Forge

The parent Projects engineering standard remains applicable. This file records local commands and constraints; it does not replace that standard.

## Project

Single-user document workspace for local Ollama inference. Python 3.12, uv, FastAPI, Pydantic, SQLite, PyMuPDF/Tesseract, vanilla JavaScript, and OpenTelemetry. Exact dependency versions are in `uv.lock`. Risk: medium, because documents and generated answers are untrusted. Shared agent memory is disabled. Attribution policy: no AI trailers or generated-by notices. Commit and publish only with explicit authorization.

Run all commands from the project root on the host. Use `.cache/` for disposable artifacts and `.data/` for local application data. Never inspect personal uploads during development; use the synthetic corpus and temporary fixtures.

## Commands

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.cache/python"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
uv sync --frozen
sh scripts/ollama.sh
# Separate terminal; networked model setup:
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:4b
OLLAMA_HOST=127.0.0.1:11435 ollama pull nomic-embed-text
uv run --frozen python -m playwright install chromium
sh scripts/run.sh
# Scoped check:
uv run --frozen pytest -q tests/test_provider.py
# Full verification: starts test servers, scans advisories over the network,
# and runs real local models; requires Ollama already running; potentially slow.
sh scripts/verify.sh
```

## Entry points and invariants

- `forge/app.py`: HTTP contracts and local-origin boundary. Bind only to loopback.
- `forge/service.py`: ingestion, state, cancellation, and deletion. Run one application worker.
- `forge/db.py`: schema and transactions. Do not silently migrate an unknown schema.
- `forge/ollama.py`: allowlist, retries, structured output, exact source-quote validation.
- `tests/`: deterministic application/provider tests and browser acceptance.
- `evaluation/PROTOCOL.md`: frozen real-model protocol. Preserve failed runs; do not tune expectations to results.

No production access, cloud inference, paid APIs, autonomous tool execution, or personal/customer evaluation data. Document changes accurately; do not turn planned integrations into implemented claims. A fake model test never establishes real-model answer quality. Two vendor constructor calls have narrowly scoped typing exceptions because PyMuPDF does not annotate those constructors; all application modules remain under strict mypy checks.
