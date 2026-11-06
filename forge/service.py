"""Bounded ingestion and question workers, with durable state and cancellation."""

import asyncio
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from forge.config import EMBED_MODEL, INDEX_VERSION, PROMPT_VERSION, Settings
from forge.db import Database, decode_run
from forge.extract import chunk_text
from forge.ollama import ModelError, Ollama, validate_answer
from forge.retrieval import retrieve
from forge.telemetry import configure

log = logging.getLogger("forge")
TERMINAL = {"completed", "failed", "cancelled", "interrupted", "redacted"}


class Service:
    def __init__(self, settings: Settings, provider: Ollama | None = None):
        self.settings = settings
        self.files = settings.data_dir / "uploads"
        self.files.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.data_dir / "forge.sqlite3")
        self.provider = provider or Ollama(settings.ollama_url)
        self.telemetry = configure(settings.data_dir)
        self.tracer = self.telemetry.get_tracer("forge", "0.1.0")
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.run_gate = asyncio.Semaphore(1)
        self.ingest_gate = asyncio.Semaphore(1)
        self.upload_lock = asyncio.Lock()
        self.lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        for row in self.db.rows("SELECT id FROM runs WHERE status IN ('queued','running')"):
            self.db.update_run(
                row["id"],
                status="interrupted",
                checkpoint="interrupted",
                error="The application stopped before this answer completed. Submit it again.",
                answer=None,
                citations="[]",
            )
            self.db.event(row["id"], "done", {"status": "interrupted"})
        for row in self.db.rows(
            "SELECT id FROM documents WHERE status IN ('queued','extracting','embedding')"
        ):
            self.spawn("doc:" + row["id"], self.ingest(row["id"]))
        known = {row["id"] for row in self.db.rows("SELECT id FROM documents")}
        for file in self.files.iterdir():
            if file.is_file() and file.name not in known:
                file.unlink()

    def spawn(self, key: str, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks[key] = task
        task.add_done_callback(lambda _: self.tasks.pop(key, None))

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.provider.close()
        self.telemetry.shutdown()

    async def parse(self, path: Path, suffix: str, probe: bool = False) -> dict[str, Any]:
        args = [sys.executable, "-m", "forge.extract", str(path), suffix]
        if probe:
            args.append("--probe")
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(self.settings.ingest_timeout):
                stdout, _ = await proc.communicate()
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        try:
            result: dict[str, Any] = json.loads(stdout)
        except (ValueError, TypeError) as exc:
            raise ValueError("Document parser stopped without a valid result.") from exc
        if proc.returncode or "error" in result:
            raise ValueError(result.get("error", "Document parsing failed."))
        return result

    def documents(self) -> list[dict[str, Any]]:
        rows = self.db.rows("SELECT * FROM documents ORDER BY created_at DESC,id DESC")
        for row in rows:
            row["warnings"] = json.loads(row["warnings"])
            row["pages"] = self.db.one(
                "SELECT count(*) AS n FROM pages WHERE document_id=?",
                (row["id"],),
            )["n"]  # type: ignore[index]
        return rows

    async def add_document(self, name: str, suffix: str, content: bytes) -> dict[str, Any]:
        if len(content) > self.settings.max_upload:
            raise ValueError("Files must be 20 MB or smaller.")
        digest = hashlib.sha256(content).hexdigest()
        async with self.upload_lock:
            existing = self.db.one("SELECT * FROM documents WHERE hash=?", (digest,))
            if existing:
                return {"id": existing["id"], "duplicate": True, "status": existing["status"]}
            if len(self.tasks) >= 10:
                raise ValueError("The local work queue is full. Wait for a task to finish.")
            document_id = uuid4().hex
            path = self.files / document_id
            path.write_bytes(content)
            try:
                await self.parse(path, suffix, probe=True)
                with self.db.connection() as con:
                    version = con.execute(
                        "SELECT COALESCE(MAX(version),0)+1 FROM documents WHERE name=?",
                        (name,),
                    ).fetchone()[0]
                    con.execute(
                        "INSERT INTO documents(id,name,hash,version,suffix,status) "
                        "VALUES(?,?,?,?,?,?)",
                        (document_id, name, digest, version, suffix, "queued"),
                    )
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            self.spawn("doc:" + document_id, self.ingest(document_id))
            return {"id": document_id, "duplicate": False, "status": "queued"}

    async def ingest(self, document_id: str) -> None:
        start = time.perf_counter()
        try:
            async with asyncio.timeout(self.settings.ingest_timeout):
                async with self.ingest_gate:
                    with self.tracer.start_as_current_span(
                        "ingestion",
                        attributes={"document.id": document_id},
                        record_exception=False,
                        set_status_on_exception=False,
                    ):
                        row = self.db.one("SELECT * FROM documents WHERE id=?", (document_id,))
                        if not row:
                            return
                        self.db.execute(
                            "UPDATE documents SET status='extracting',error=NULL WHERE id=?",
                            (document_id,),
                        )
                        pages = self.db.rows(
                            "SELECT number,text,ocr FROM pages WHERE document_id=? ORDER BY number",
                            (document_id,),
                        )
                        warnings = json.loads(row["warnings"])
                        if not pages:
                            with self.tracer.start_as_current_span(
                                "extraction",
                                record_exception=False,
                                set_status_on_exception=False,
                            ):
                                result = await self.parse(self.files / document_id, row["suffix"])
                            pages, warnings = result["pages"], result["warnings"]
                            with self.db.connection() as con:
                                con.executemany(
                                    "INSERT INTO pages VALUES(?,?,?,?)",
                                    [
                                        (document_id, p["number"], p["text"], p["ocr"])
                                        for p in pages
                                    ],
                                )
                                con.execute(
                                    "UPDATE documents SET warnings=?,extraction_ms=? WHERE id=?",
                                    (
                                        json.dumps(warnings),
                                        (time.perf_counter() - start) * 1000,
                                        document_id,
                                    ),
                                )
                        self.db.execute(
                            "UPDATE documents SET status='embedding' WHERE id=?",
                            (document_id,),
                        )
                        with self.tracer.start_as_current_span(
                            "embedding",
                            record_exception=False,
                            set_status_on_exception=False,
                        ):
                            models = await self.provider.models()
                            chunks = [
                                (p["number"], text) for p in pages for text in chunk_text(p["text"])
                            ]
                            if len(chunks) > 5000:
                                raise ValueError("The document exceeds the 5000-chunk limit.")
                            vectors: list[list[float]] = []
                            for offset in range(0, len(chunks), 16):
                                vectors.extend(
                                    await self.provider.embed(
                                        [text for _, text in chunks[offset : offset + 16]]
                                    )
                                )
                        # Atomically replace derived data; retries never duplicate chunks.
                        with self.db.connection() as con:
                            con.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                            con.executemany(
                                "INSERT INTO chunks VALUES(?,?,?,?,?,?)",
                                [
                                    (
                                        f"{document_id}:{i}",
                                        document_id,
                                        page,
                                        i,
                                        text,
                                        json.dumps(vector),
                                    )
                                    for i, ((page, text), vector) in enumerate(
                                        zip(chunks, vectors, strict=True)
                                    )
                                ],
                            )
                            con.execute(
                                "UPDATE documents SET status='ready',embedding_digest=? WHERE id=?",
                                (models[EMBED_MODEL], document_id),
                            )
        except asyncio.CancelledError:
            raise
        except (ValueError, ModelError, TimeoutError) as exc:
            self.db.execute(
                "UPDATE documents SET status='failed',error=? WHERE id=?",
                (str(exc) or "Document processing timed out.", document_id),
            )
        except Exception:
            log.error(json.dumps({"event": "ingestion_failed", "document_id": document_id}))
            self.db.execute(
                "UPDATE documents SET status='failed',error='Unexpected processing error.' "
                "WHERE id=?",
                (document_id,),
            )

    async def ask(self, question: str, document_ids: list[str]) -> str:
        async with self.lifecycle_lock:
            if len(self.tasks) >= 10:
                raise ValueError("The local work queue is full. Wait for a task to finish.")
            ready = {r["id"] for r in self.db.rows("SELECT id FROM documents WHERE status='ready'")}
            if document_ids and not set(document_ids) <= ready:
                raise ValueError("One or more selected documents are missing or not ready.")
            if not ready:
                raise ValueError(
                    "Add a document and wait until it is ready before asking a question."
                )
            run_id = uuid4().hex
            self.db.execute(
                "INSERT INTO runs(id,question,document_ids,status) VALUES(?,?,?,'queued')",
                (run_id, question, json.dumps(document_ids)),
            )
            self.db.event(run_id, "progress", {"message": "Waiting for the local model"})
            self.spawn("run:" + run_id, self.run(run_id))
            return run_id

    async def run(self, run_id: str) -> None:
        start = time.perf_counter()
        timings: dict[str, float] = {}
        try:
            async with asyncio.timeout(self.settings.run_timeout):
                async with self.run_gate:
                    if not self.db.update_run(run_id, status="running", checkpoint="retrieval"):
                        return
                    with self.tracer.start_as_current_span(
                        "question",
                        attributes={"run.id": run_id},
                        record_exception=False,
                        set_status_on_exception=False,
                    ):
                        row = self.db.one("SELECT * FROM runs WHERE id=?", (run_id,))
                        assert row
                        models = await self.provider.models()
                        versions = {
                            "models": models,
                            "prompt": PROMPT_VERSION,
                            "index": INDEX_VERSION,
                        }
                        self.db.update_run(run_id, versions=json.dumps(versions))
                        self.db.event(run_id, "progress", {"message": "Finding relevant passages"})
                        tick = time.perf_counter()
                        with self.tracer.start_as_current_span(
                            "retrieval",
                            record_exception=False,
                            set_status_on_exception=False,
                        ):
                            vector = (await self.provider.embed([row["question"]], query=True))[0]
                            evidence = retrieve(
                                self.db,
                                row["question"],
                                vector,
                                json.loads(row["document_ids"]),
                                models[EMBED_MODEL],
                            )
                        if not evidence:
                            raise ValueError("No indexed passages are available for this question.")
                        timings["retrieval_ms"] = (time.perf_counter() - tick) * 1000
                        self.db.update_run(
                            run_id,
                            evidence=json.dumps(evidence),
                            checkpoint="generation",
                            timings=json.dumps(timings),
                        )
                        self.db.event(
                            run_id, "progress", {"message": "Reading and checking sources"}
                        )
                        raw = ""
                        with self.tracer.start_as_current_span(
                            "generation",
                            record_exception=False,
                            set_status_on_exception=False,
                        ):
                            async for piece in self.provider.generate(row["question"], evidence):
                                if not raw:
                                    timings["first_token_ms"] = (time.perf_counter() - start) * 1000
                                    self.db.event(
                                        run_id,
                                        "progress",
                                        {
                                            "message": "Receiving model output; checking citations",
                                        },
                                    )
                                raw += piece
                        answer = validate_answer(raw, evidence)
                        # Confirm the tag still resolves to the same models after generation.
                        if await self.provider.models() != models:
                            raise ModelError("Model identity changed during the run. Retry it.")
                        self.db.update_run(run_id, checkpoint="validated")
                        citations = []
                        for c in answer.citations:
                            source = next(e for e in evidence if e["id"] == c.id)
                            citations.append(
                                {
                                    "id": c.id,
                                    "quote": c.quote,
                                    "document_id": source["document_id"],
                                    "name": source["name"],
                                    "page": source["page"],
                                    "version": source["version"],
                                }
                            )
                        # Stream only checked text; raw structured JSON never reaches the browser.
                        for offset in range(0, len(answer.answer), 80):
                            self.db.event(
                                run_id, "answer", {"text": answer.answer[offset : offset + 80]}
                            )
                            await asyncio.sleep(0)
                        timings["total_ms"] = (time.perf_counter() - start) * 1000
                        self.db.update_run(
                            run_id,
                            status="completed",
                            checkpoint="completed",
                            answer=answer.answer,
                            citations=json.dumps(citations),
                            abstained=int(answer.abstained),
                            timings=json.dumps(timings),
                        )
        except asyncio.CancelledError:
            self.db.update_run(
                run_id,
                status="cancelled",
                checkpoint="cancelled",
                error="Generation was cancelled. No complete answer was saved.",
                answer=None,
            )
            raise
        except (ValueError, ModelError, TimeoutError) as exc:
            timings["total_ms"] = (time.perf_counter() - start) * 1000
            self.db.update_run(
                run_id,
                status="failed",
                checkpoint="failed",
                answer=None,
                citations="[]",
                error=str(exc)
                or "The 120-second run deadline was exceeded. The answer is incomplete.",
                timings=json.dumps(timings),
            )
        except Exception:
            log.error(json.dumps({"event": "run_failed", "run_id": run_id}))
            self.db.update_run(
                run_id,
                status="failed",
                checkpoint="failed",
                answer=None,
                error="An unexpected local error stopped the answer.",
            )
        finally:
            row = self.db.one("SELECT status FROM runs WHERE id=?", (run_id,))
            if row:
                self.db.event(run_id, "done", {"status": row["status"]})
                log.info(
                    json.dumps({"event": "run_finished", "run_id": run_id, "status": row["status"]})
                )

    async def cancel(self, run_id: str) -> None:
        self.db.update_run(
            run_id,
            status="cancelled",
            checkpoint="cancelled",
            answer=None,
            error="Generation was cancelled. No complete answer was saved.",
        )
        task = self.tasks.get("run:" + run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def delete_document(self, document_id: str) -> None:
        async with self.lifecycle_lock:
            # In-flight retrieval may not yet have persisted its source IDs. Stop it first.
            for run in self.db.rows("SELECT id FROM runs WHERE status IN ('queued','running')"):
                await self.cancel(run["id"])
            task = self.tasks.get("doc:" + document_id)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            affected = []
            for row in self.db.rows("SELECT * FROM runs"):
                run = decode_run(row)
                if (
                    document_id in run["document_ids"]
                    or any(e["document_id"] == document_id for e in run["evidence"])
                    or (not run["document_ids"] and run["status"] != "completed")
                ):
                    affected.append(row["id"])
            with self.db.connection() as con:
                (self.files / document_id).unlink(missing_ok=True)
                for run_id in affected:
                    con.execute("DELETE FROM events WHERE run_id=?", (run_id,))
                    con.execute(
                        "UPDATE runs SET question='',document_ids='[]',answer=NULL,citations='[]',"
                        "evidence='[]',error=NULL,status='redacted',checkpoint='redacted' "
                        "WHERE id=?",
                        (run_id,),
                    )
                con.execute("DELETE FROM documents WHERE id=?", (document_id,))
            # Logical deletion, not a promise of forensic disk erasure.
            with self.db.connection() as con:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
