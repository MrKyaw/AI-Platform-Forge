# AI Platform Forge

Read local documents with an AI model, then check the passages behind its answers. Upload a PDF, Markdown file, or text file, ask a question, and inspect its sources and run history. Documents and inference stay on your machine.

The application uses FastAPI, SQLite full-text search, local embeddings, and Ollama. It combines keyword and vector rankings, keeps page references, and checks structured answers and source quotes before displaying answer text. A checked citation can still be used incorrectly by a model; read the source before relying on an answer.

Current release: `0.1.0`. See the [releases](https://github.com/MrKyaw/AI-Platform-Forge/releases) and [changelog](docs/Results.md).

## Get started

You need Python 3.12 (or allow uv to download it), `uv`, Ollama, and Tesseract with English language data on PATH. Node is used only for JavaScript syntax checks. Chromium is downloaded locally for browser tests. The initial model downloads are roughly 3 GB; allow additional disk space for Python packages and test browsers. Low-memory machines may be slow, especially during first model load.

From the project directory:

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.cache/python"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
uv sync --frozen
uv run --frozen python -m playwright install chromium
```

In a separate terminal, start the isolated model server:

```sh
sh scripts/ollama.sh
```

Download the models into that server's project-local storage:

```sh
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:4b
OLLAMA_HOST=127.0.0.1:11435 ollama pull nomic-embed-text
```

Then start the app:

```sh
sh scripts/run.sh
```

Open [the local workspace](http://127.0.0.1:8000). Add a file and wait for its status to become `ready`. Choose documents to filter a question, or leave them unchecked to search the whole library. Ask a question and click a citation to read its passage. Stop cancels active generation. Recent questions survive an application restart.

Setup and model/browser downloads require network access. Running the app and inference does not require an external service. The scripts bind only to loopback. Do not expose this single-user application to a network or run multiple application workers against its database.

## Verification

```sh
# Fast, deterministic application checks (includes OCR; no real model calls)
uv run --frozen pytest -q tests/test_core.py tests/test_provider.py tests/test_application.py
# One reproducing test
uv run --frozen pytest -q 'tests/test_application.py::test_failure_never_accepts_an_answer[citation]'
# Browser journeys against an isolated local server and a fake model
uv run --frozen pytest -q tests/test_browser.py
# All checks, real model smoke test, and the full 30-question evaluation
sh scripts/verify.sh
```

The full verification command needs the local Ollama server and downloaded models. Vulnerability scanning contacts the public package advisory service and transmits package names/versions, not your source or documents. Evaluation can take several minutes on a small Mac. Each run gets a new directory under `.cache/evaluations/`; it retains its corpus-backed SQLite run records, answers, failures, model digests, and source hash. A partial evaluation cannot pass the release gate.

See [the test report](docs/Results.md) for actual results and limitations, [the evaluation protocol](evaluation/PROTOCOL.md) for the frozen acceptance set, and [the local architecture](docs/Architecture.md) for data flow and recovery.

## Limits and troubleshooting

- Files: UTF-8 `.txt`/`.md` or unencrypted PDFs, at most 20 MB and 100 PDF pages. Extraction is capped at two million characters and 5,000 chunks. Scanned pages use English OCR with warnings; tables and difficult scans need manual checking.
- Chunk lengths use whitespace-token estimates, not exact model tokenization. Five passages are sent to the answer model. Unusually token-dense inputs can exceed its context; such errors fail the run rather than falling back to a different model.
- Model unavailable: check `OLLAMA_HOST=127.0.0.1:11435 ollama list` and `/api/ready`. The app gives the required pull command when a model is missing. It never downloads a model automatically.
- Interrupted stream or model outage: the question is marked failed or interrupted; submit it again. No unfinished answer is saved as complete. Retries are limited to transient failures before response content arrives.
- Failed indexing: fix the model/OCR problem, then choose **Retry indexing**. Restarting the app resumes interrupted ingestion without duplicate chunks. If the embedding model digest changed, delete and re-upload affected documents to rebuild their indexes.
- Deleting a document stops active questions and removes derived source content and saved answers that used it. Minimal run metadata remains. This is logical deletion, not forensic secure erasure; backups and disk recovery are outside the app's control.
- Local traces are in `.data/traces.jsonl`, rotated at 5 MB with two backups. They contain identifiers and timings, not source text, questions, or answers. SQLite and uploads do contain your document/question/answer content; protect the local data directory.
- A restart marks unfinished questions interrupted rather than automatically replaying generation. Completed questions remain available. The app does not execute tools or model-generated commands.

Stop the app before backing up `.data/` as a complete directory. Restore to a separate directory and run with `FORGE_DATA_DIR` pointing to it; do not mix SQLite files from different backups. A schema version mismatch stops startup. Never copy live database files individually or replace data while the app runs.

## Project documents

[Requirements](docs/PRD.md) · [Skills](docs/Skills.md) · [Architecture](docs/Architecture.md) · [Roadmap](docs/Roadmap.md) · [Evaluation](docs/Evaluation.md)

Cloud integrations, multi-user accounts, MLOps, GPU scheduling, and ROS belong to later releases. Project code is provided under the existing [MIT license](LICENSE). Third-party dependencies retain their own licenses. PyMuPDF has licensing conditions that must be reviewed before redistribution or commercial use; dependency scanning is not a license or security certification.
