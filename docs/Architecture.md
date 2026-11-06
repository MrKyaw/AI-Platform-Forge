# How the local application works

The application runs as one FastAPI process on localhost. SQLite stores document versions, extracted pages, chunks, embeddings, questions, events, checkpoints, and citations. Uploaded files live in `.data/uploads/`. Ollama runs separately on port 11435 and uses the two allowlisted models.

## From a file to an answer

1. The upload endpoint checks the extension and size, hashes the file, and validates its format. Identical content returns the existing document instead of creating a duplicate. Changed content with the same filename creates a new version.
2. A bounded worker extracts UTF-8 text or PDF pages in a separate process. Scanned PDF pages use English Tesseract OCR. Page references, extraction warnings, and timing are preserved. Extraction has CPU, wall-clock, page, text, and chunk limits.
3. Markdown headings start fresh sections. Chunks target 500 whitespace tokens with 75-token overlap and never cross page boundaries. Ollama creates embeddings. Derived chunks and the ready status are committed together.
4. A question embeds its query, ranks passages using SQLite full-text search and cosine similarity, and combines the two rankings with reciprocal rank fusion. Filters apply to both rankings. Duplicate passages are removed and five passages are retained.
5. The answer model receives the question and passages as untrusted data. It has no tools, shell, filesystem, or cloud capabilities. Structured output must contain an answer, citation IDs with exact supporting quotes, and an abstention flag.
6. The application validates the complete structured result before streaming checked answer text to the browser. Unknown citations, invented quotes, malformed output, and interrupted streams fail the run. A checked quote does not prove the model's interpretation is correct.

## State and recovery

Documents move through queued, extracting, embedding, and ready or failed states. Extracted pages survive embedding failures. Retry and startup recovery replace derived chunks atomically without duplicating them.

Questions move from queued to running, then completed, failed, cancelled, or interrupted. Checkpoints record retrieval, generation, and validation. The 120-second deadline includes queue time. Generation is serial; transient model failures allow two retries before any answer content has arrived. Cancellation closes the active model stream. Startup marks unfinished questions interrupted rather than replaying them automatically.

Deleting a document stops active questions, removes the source file and derived rows, and clears stored questions, evidence, events, citations, and answers associated with that source. Minimal run metadata remains. SQLite deletion is logical, not forensic secure erasure.

## Local boundaries

The server binds to loopback, checks Host and Origin, rejects cross-site mutations, and sends a restrictive content security policy. The interface renders document and answer content as text. There are no accounts, remote providers, model-generated actions, or production deployment controls in this release. Run one application worker; multiple processes would not share its work queue or cancellation registry.

Model URLs must be loopback HTTP addresses. Every material run records model digests and prompt/index versions. A changed embedding digest blocks retrieval until affected documents are rebuilt. Model identity is checked again after generation.

OpenTelemetry writes local, rotating JSON spans for ingestion, extraction, embeddings, retrieval, and generation. Run IDs correlate question spans. Exception payloads and document/question/answer content are excluded from traces. Trace export failures do not authorize model actions or change application policy.

## Interfaces

Interactive API documentation is at `/docs`. The application exposes document upload/list/status/delete/retry, question submission, run history/status/cancellation, resumable server-sent events, source passages, health, and model readiness. Models cannot be selected through request bodies. Event IDs allow a client to resume a live stream without replaying earlier events.

## Later work

Cloud adapters, tenant authorization, durable distributed queues, knowledge graphs, MLOps, GPU scheduling, Application Insights export, and ROS simulation remain separate milestones. They are not implemented by the local application. See [Roadmap.md](Roadmap.md).
