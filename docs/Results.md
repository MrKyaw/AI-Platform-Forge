# Verification results

Checked on 2026-11-06 on an Apple Silicon Mac with 8 GB of memory, macOS 26.0, Python 3.12.8, and Tesseract 5.5.1. This report belongs to the commit containing it.

The application and browser suite passes. The broader local-model acceptance gate remains incomplete; this is a development build, not a fully validated release.

## Checks run

| Check | Command | Result |
|---|---|---|
| Formatting | `.venv/bin/ruff format --check forge scripts tests` | Passed; 18 files |
| Lint | `.venv/bin/ruff check forge scripts tests` | Passed |
| Strict typing | `.venv/bin/mypy forge scripts` | Passed; 12 source files |
| JavaScript syntax | `node --check forge/static/app.js` | Passed |
| Application and browser tests | `PLAYWRIGHT_BROWSERS_PATH=.cache/ms-playwright .venv/bin/pytest -q --cov --cov-report=term --cov-report=json:.cache/coverage.json` | 45 passed in 17.48 seconds; five PyMuPDF binding deprecation warnings |
| Coverage | Parent-process statement/branch measurement from that test run | 85% combined; parser subprocess coverage is not included |
| Python compilation | `.venv/bin/python -m compileall -q forge scripts` | Passed |
| Dependency scan | `.venv/bin/pip-audit --format json --output .cache/dependency-audit.json` | 63 installed packages checked; no known vulnerabilities reported |
| Documentation links | `.venv/bin/python -m scripts.check_docs` | Passed; nine Markdown files and 26 local links |
| Real-model smoke | Direct invocation of the Ollama adapter against the isolated local server | Passed: 768-dimensional embedding and a structured answer citing an exact source quote |
| Full real-model evaluation | `.venv/bin/python -m scripts.evaluate --output .cache/evaluations/initial` | Interrupted after 6 completed cases; cannot pass the release gate |

The 45-test suite covers application behavior with a deterministic model fake, transport contracts, digital/scanned/encrypted/overlong PDFs, citation rejection, deadlines, cancellation, deletion, persistence/recovery, and two full-browser journeys. Browser checks include narrow layouts and keyboard navigation. A desktop screenshot was also visually inspected. These tests do not establish real-model answer quality.

## Model identities

- `qwen3:4b`: `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`
- `nomic-embed-text`: `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`

The final application/corpus/lockfile SHA-256, computed by `scripts.evaluate.source_hash`, is `7f5735400edbea72360da78963c8e783a8039cba2cda808f1dfedf1ec42295ed`. It does not include documentation, tests, or static assets. The interrupted evaluation recorded its earlier source hash, `7384749717ea4ee4f5595049892511630c669e169b2d8050e057d3936b8fee51`; it must not be represented as a full evaluation of the final commit.

## Retained evaluation outcomes

| Case | Outcome | Elapsed |
|---|---|---|
| Aurora-code | Failed | 124.0 s |
| Aurora-retention | Passed | 103.9 s |
| Boreal-code | Passed | 77.1 s |
| Boreal-retention | Passed | 57.7 s |
| Cobalt-code | Passed | 69.1 s |
| Cobalt-retention | Passed | 55.1 s |

The first question exceeded the 120-second deadline during model loading and host resource contention. Later questions completed, but the run was interrupted to separate model evaluation from browser testing. Five passed cases out of six completed cases do not establish the 30-case quality, retrieval, or adversarial targets. Per-case data and the evaluation database remain in the ignored local evaluation directory; no aggregate passing result exists.

The initial application run had one upload-wait timeout (42 passed, one failed). That case passed on rerun after avoiding unnecessary PDF-library loading for text documents. The initial headless-shell browser stalled and later crashed because its GPU subprocess could not locate ICU data. The full Chromium build passed both browser journeys, followed by the complete 45-test run. Assertions and timeouts were not weakened.

## Remaining work

Run the complete frozen evaluation on the final source revision and investigate every failed case. Independent human answer review, calibrated confidence, subgroup/fairness studies, backup/restore rehearsal, and the later cloud/ML/GPU/ROS work have not been completed. No production deployment or production-readiness claim is made.
