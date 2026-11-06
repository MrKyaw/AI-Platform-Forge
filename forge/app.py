"""HTTP boundary for the single-user, loopback-only workspace."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from forge.config import Settings
from forge.db import decode_run
from forge.ollama import ModelError, Ollama
from forge.service import TERMINAL, Service

BASE = Path(__file__).parent


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a question.")
        return value.strip()

    @field_validator("document_ids")
    @classmethod
    def valid_ids(cls, values: list[str]) -> list[str]:
        if any(
            len(value) != 32 or any(c not in "0123456789abcdef" for c in value) for value in values
        ):
            raise ValueError("Invalid document ID")
        return list(dict.fromkeys(values))


def create_app(settings: Settings | None = None, provider: Ollama | None = None) -> FastAPI:
    config = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service = Service(config, provider)
        app.state.service = service
        await service.start()
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="AI Platform Forge", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")

    @app.middleware("http")
    async def local_boundary(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse(
                {"detail": "Cross-origin requests are not permitted."}, status_code=403
            )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "Cross-site requests are not permitted."}, status_code=403
                )
            if request.method == "POST" and not request.headers.get("content-type", "").startswith(
                ("application/json", "multipart/form-data")
            ):
                return JSONResponse({"detail": "Use JSON or a multipart upload."}, status_code=415)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def service(request: Request) -> Service:
        return request.app.state.service  # type: ignore[no-any-return]

    def run_or_404(svc: Service, run_id: str) -> dict[str, Any]:
        row = svc.db.one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not row:
            raise HTTPException(404, "Run not found.")
        return decode_run(row)

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/ready")
    async def ready(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(5):
                models = await service(request).provider.models()
            return JSONResponse({"status": "ready", "models": models})
        except (ModelError, TimeoutError) as exc:
            return JSONResponse(
                {"status": "unavailable", "detail": str(exc) or "Ollama readiness timed out."},
                status_code=503,
            )

    @app.get("/api/documents")
    async def documents(request: Request) -> list[dict[str, Any]]:
        return service(request).documents()

    @app.get("/api/documents/{document_id}")
    async def document(request: Request, document_id: str) -> dict[str, Any]:
        item = next((d for d in service(request).documents() if d["id"] == document_id), None)
        if not item:
            raise HTTPException(404, "Document not found.")
        return item

    @app.post("/api/documents", status_code=202)
    async def upload(request: Request, file: UploadFile) -> dict[str, Any]:
        name = Path((file.filename or "").replace("\\", "/")).name
        suffix = Path(name).suffix.lower()
        if suffix not in {".txt", ".md", ".pdf"} or len(name) > 200:
            raise HTTPException(
                422, "Upload a .txt, .md, or .pdf file with a name under 200 characters."
            )
        content = bytearray()
        try:
            while piece := await file.read(65536):
                content.extend(piece)
                if len(content) > config.max_upload:
                    raise HTTPException(413, "Files must be 20 MB or smaller.")
            try:
                return await service(request).add_document(name, suffix, bytes(content))
            except (ValueError, TimeoutError) as exc:
                raise HTTPException(422, str(exc) or "Document validation timed out.") from exc
        finally:
            await file.close()

    @app.post("/api/documents/{document_id}/retry", status_code=202)
    async def retry_document(request: Request, document_id: str) -> dict[str, str]:
        svc = service(request)
        async with svc.lifecycle_lock:
            row = svc.db.one("SELECT status FROM documents WHERE id=?", (document_id,))
            if not row:
                raise HTTPException(404, "Document not found.")
            if row["status"] != "failed":
                raise HTTPException(409, "Only failed documents can be retried.")
            if len(svc.tasks) >= 10:
                raise HTTPException(429, "The local queue is full.")
            svc.db.execute(
                "UPDATE documents SET status='queued',error=NULL WHERE id=?", (document_id,)
            )
            svc.spawn("doc:" + document_id, svc.ingest(document_id))
        return {"status": "queued"}

    @app.delete("/api/documents/{document_id}")
    async def delete_document(request: Request, document_id: str) -> dict[str, str]:
        svc = service(request)
        if not svc.db.one("SELECT id FROM documents WHERE id=?", (document_id,)):
            raise HTTPException(404, "Document not found.")
        await svc.delete_document(document_id)
        return {"status": "deleted"}

    @app.post("/api/questions", status_code=202)
    async def ask(request: Request, body: Question) -> dict[str, str]:
        try:
            run_id = await service(request).ask(body.question, body.document_ids)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"id": run_id, "status": "queued"}

    @app.get("/api/runs")
    async def runs(request: Request) -> list[dict[str, Any]]:
        return [
            decode_run(row)
            for row in service(request).db.rows(
                "SELECT * FROM runs ORDER BY created_at DESC,id DESC LIMIT 100"
            )
        ]

    @app.get("/api/runs/{run_id}")
    async def run(request: Request, run_id: str) -> dict[str, Any]:
        return run_or_404(service(request), run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(request: Request, run_id: str) -> dict[str, Any]:
        svc = service(request)
        run_or_404(svc, run_id)
        await svc.cancel(run_id)
        return run_or_404(svc, run_id)

    @app.get("/api/runs/{run_id}/events")
    async def events(request: Request, run_id: str) -> StreamingResponse:
        svc = service(request)
        run_or_404(svc, run_id)
        try:
            cursor = int(request.headers.get("last-event-id", "0"))
            if cursor < 0:
                raise ValueError("negative")
        except ValueError as exc:
            raise HTTPException(422, "Invalid event cursor.") from exc

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            while not await request.is_disconnected():
                current = run_or_404(svc, run_id)
                if current["status"] == "redacted":
                    yield 'event: done\ndata: {"status":"redacted"}\n\n'
                    return
                for row in svc.db.rows(
                    "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                    (run_id, cursor),
                ):
                    cursor = row["seq"]
                    yield f"id: {cursor}\nevent: {row['kind']}\ndata: {row['payload']}\n\n"
                if current["status"] in TERMINAL:
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.15)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/sources/{chunk_id}")
    async def source(request: Request, chunk_id: str) -> dict[str, Any]:
        row = service(request).db.one(
            "SELECT c.id,c.document_id,c.page,c.text,d.name,d.version FROM chunks c "
            "JOIN documents d ON d.id=c.document_id WHERE c.id=? AND d.status='ready'",
            (chunk_id,),
        )
        if not row:
            raise HTTPException(404, "Source not found or deleted.")
        return row

    return app


app = create_app()
