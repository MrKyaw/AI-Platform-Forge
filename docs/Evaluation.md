# How we test the application

The deterministic suite checks extraction, chunking, hybrid ranking, model boundaries, schema and citation validation, request validation, retries, cancellation, deadlines, run-state transitions, deletion, and restart recovery. Integration tests create digital, scanned, encrypted, and overlong PDF fixtures. Model transport tests simulate malformed streams, missing models, outages, and rate limits.

Browser tests use an isolated application server and a deterministic model fake. They cover upload, questions, citations, cancellation, deletion, history after restart, keyboard navigation, and narrow layouts. Their results establish interface behavior, not real-model quality.

The separate local-model smoke test checks the requested model digests, embedding dimensions, structured generation, and exact source-quote validation. The full evaluation uses the frozen synthetic corpus and 30 labeled cases in [the protocol](../evaluation/PROTOCOL.md). It requires Recall@5 of at least 0.85, an expected-answer check rate of at least 0.90, a supported factual-answer rate of at least 0.90, valid citations, and every defined adversarial case passing. Errors count as failures.

## Running the checks

Use the commands in [README.md](../README.md). `scripts/verify.sh` runs formatting, linting, strict typing, JavaScript syntax, application and browser tests with coverage, local documentation links, Python compilation, dependency scanning, the real-model smoke test, and the full evaluation. It stops on the first failed command.

Each evaluation creates a new directory under `.cache/evaluations/`. Preserve its SQLite records, per-case JSON, source hash, corpus version, and model digests. Do not alter expected answers after observing results. Incomplete evaluations cannot pass.

## Interpreting the results

See [Results.md](Results.md) for observed outcomes. Coverage is measured separately from test pass rate. Parsing runs in subprocesses, whose execution is not included in the current parent-process coverage measurement. PDF and OCR integration assertions still exercise those subprocesses.

Expected-term checks on a small synthetic corpus are an acceptance tool, not independent human judgment or evidence of production safety. A valid exact quote can still fail to support an interpretation. Broader groundedness, fairness, calibration, content safety, and provider comparisons remain future work.

The application has no tool execution capability. Its prompt-injection tests assess response behavior and the fixed absence of side-effecting tools; they cannot establish immunity to every attack. Scanned/table-heavy documents and unusual token-dense inputs need particular care.
