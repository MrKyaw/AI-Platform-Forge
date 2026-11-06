import asyncio
import json
from pathlib import Path

import pymupdf
import pytest

from forge.config import Settings
from forge.db import Database
from forge.service import Service
from tests.conftest import FakeOllama, upload_ready, wait_document, wait_run


async def test_upload_answer_sources_events_and_deletion(workspace) -> None:
    client, svc, _ = workspace
    document_id = await upload_ready(client)
    duplicate = await client.post(
        "/api/documents",
        files={
            "file": ("renamed.txt", b"# Launch\nThe launch code is cedar."),
        },
    )
    assert duplicate.json()["duplicate"]
    assert len((await client.get("/api/documents")).json()) == 1
    response = await client.post("/api/questions", json={"question": "What is the launch code?"})
    run_id = response.json()["id"]
    run = await wait_run(client, run_id)
    assert run["status"] == "completed", run
    assert run["answer"] == "The launch code is cedar."
    assert run["versions"]["models"]["qwen3:4b"] == "chat-test-digest"
    assert set(run["timings"]) == {"retrieval_ms", "first_token_ms", "total_ms"}
    source_id = run["citations"][0]["id"]
    assert (await client.get("/api/sources/" + source_id)).json()["page"] == 1
    events = await client.get(f"/api/runs/{run_id}/events")
    assert "event: answer" in events.text and "event: done" in events.text
    assert (
        "event: answer"
        not in (
            await client.get(
                f"/api/runs/{run_id}/events",
                headers={"last-event-id": "999"},
            )
        ).text
    )
    assert (
        await client.get(f"/api/runs/{run_id}/events", headers={"last-event-id": "bad"})
    ).status_code == 422
    await client.delete("/api/documents/" + document_id)
    run = (await client.get("/api/runs/" + run_id)).json()
    assert run["status"] == "redacted"
    assert not run["question"] and not run["answer"] and not run["evidence"]
    assert (await client.get("/api/sources/" + source_id)).status_code == 404
    assert not (svc.files / document_id).exists()
    assert svc.db.one("SELECT count(*) AS n FROM chunks")["n"] == 0
    assert svc.db.one("SELECT count(*) AS n FROM pages")["n"] == 0
    assert svc.db.one("SELECT count(*) AS n FROM chunk_search")["n"] == 0
    assert svc.db.one("SELECT count(*) AS n FROM events WHERE run_id=?", (run_id,))["n"] == 0
    traces = (svc.settings.data_dir / "traces.jsonl").read_text()
    assert run_id in traces
    assert "cedar" not in traces and "launch code" not in traces


@pytest.mark.parametrize("kind", ["generate", "schema", "citation", "models"])
async def test_failure_never_accepts_an_answer(workspace, kind: str) -> None:
    client, _, provider = workspace
    await upload_ready(client)
    if kind == "schema":
        provider.raw = "invalid json"
    elif kind == "citation":
        provider.raw = json.dumps(
            {
                "answer": "fabricated",
                "citations": [{"id": "foreign", "quote": "no"}],
                "abstained": False,
            }
        )
    else:
        provider.failure = kind
    response = await client.post("/api/questions", json={"question": "launch?"})
    run = await wait_run(client, response.json()["id"])
    assert run["status"] == "failed"
    assert run["answer"] is None and not run["citations"]
    assert "event: answer" not in (await client.get(f"/api/runs/{run['id']}/events")).text


async def test_cancellation_and_deletion_during_generation(workspace) -> None:
    client, _, provider = workspace
    document_id = await upload_ready(client)
    provider.delay = 10
    run_id = (await client.post("/api/questions", json={"question": "code?"})).json()["id"]
    await asyncio.sleep(0.05)
    result = await client.post(f"/api/runs/{run_id}/cancel", json={})
    assert result.json()["status"] == "cancelled"
    assert (await wait_run(client, run_id))["answer"] is None
    other_id = (await client.post("/api/questions", json={"question": "code?"})).json()["id"]
    await asyncio.sleep(0.05)
    assert (await client.delete("/api/documents/" + document_id)).status_code == 200
    assert (await wait_run(client, other_id))["status"] == "redacted"


async def test_deadline_includes_queue(tmp_path: Path) -> None:
    provider = FakeOllama()
    svc = Service(Settings(tmp_path, run_timeout=0.05), provider)
    # Populate through a real extraction/embedding worker before imposing a slow generation.
    doc = await svc.add_document("n.txt", ".txt", b"The launch code is cedar.")
    await asyncio.gather(*list(svc.tasks.values()))
    assert svc.db.one("SELECT status FROM documents WHERE id=?", (doc["id"],))["status"] == "ready"
    provider.delay = 1
    run_id = await svc.ask("code?", [])
    await asyncio.gather(*list(svc.tasks.values()))
    run = svc.db.one("SELECT * FROM runs WHERE id=?", (run_id,))
    assert run["status"] == "failed" and "deadline" in run["error"]
    await svc.close()


async def test_input_validation_and_local_boundary(workspace) -> None:
    client, _, _ = workspace
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/api/health")).json()["status"] == "ok"
    assert (await client.get("/api/ready")).status_code == 200
    assert (await client.get("/api/runs/missing")).status_code == 404
    assert (await client.get("/api/documents/missing")).status_code == 404
    assert (await client.delete("/api/documents/missing")).status_code == 404
    assert (await client.post("/api/questions", json={"question": " "})).status_code == 422
    assert (
        await client.post("/api/questions", json={"question": "q", "model": "remote"})
    ).status_code == 422
    assert (await client.post("/api/questions", json={"question": "q"})).status_code == 409
    assert (
        await client.post("/api/questions", json={"question": "q", "document_ids": ["bad"]})
    ).status_code == 422
    assert (await client.post("/api/questions", content="plain")).status_code == 415
    assert (await client.get("/api/health", headers={"host": "evil.example"})).status_code == 400
    assert (
        await client.post(
            "/api/questions",
            json={"question": "q"},
            headers={
                "origin": "https://evil.example",
            },
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/questions",
            json={"question": "q"},
            headers={
                "sec-fetch-site": "cross-site",
            },
        )
    ).status_code == 403
    assert (
        await client.post("/api/documents", files={"file": ("bad.exe", b"not text")})
    ).status_code == 422
    assert (
        await client.post("/api/documents", files={"file": ("bad.txt", b"\xff")})
    ).status_code == 422
    assert (
        await client.post("/api/documents", files={"file": ("empty.txt", b"")})
    ).status_code == 422
    assert (
        await client.post(
            "/api/documents", files={"file": ("large.txt", b"x" * (20 * 1024 * 1024 + 1))}
        )
    ).status_code == 413


def make_pdf(scanned: bool = False, encrypted: bool = False, pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((50, 80), "The launch code is cedar.", fontsize=24)
    if scanned:
        image = doc[0].get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
        doc.close()
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_image(page.rect, stream=image)
    data = (
        doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
        if encrypted
        else doc.tobytes()
    )
    doc.close()
    return data


@pytest.mark.parametrize("scanned", [False, True])
async def test_pdf_and_ocr(workspace, scanned: bool) -> None:
    client, svc, _ = workspace
    result = await client.post("/api/documents", files={"file": ("scan.pdf", make_pdf(scanned))})
    assert result.status_code == 202, result.text
    doc = await wait_document(client, result.json()["id"])
    assert doc["status"] == "ready", doc
    pages = svc.db.rows("SELECT * FROM pages WHERE document_id=?", (doc["id"],))
    assert "cedar" in pages[0]["text"].lower()
    assert bool(pages[0]["ocr"]) == scanned
    assert bool(doc["warnings"]) == scanned


async def test_reject_encrypted_overlong_and_invalid_pdf(workspace) -> None:
    client, _, _ = workspace
    for content in (make_pdf(encrypted=True), make_pdf(pages=101), b"not a PDF"):
        response = await client.post("/api/documents", files={"file": ("bad.pdf", content)})
        assert response.status_code == 422, response.text
    assert not (await client.get("/api/documents")).json()


async def test_failed_ingestion_retry_and_document_versions(workspace) -> None:
    client, svc, provider = workspace
    provider.failure = "embed"
    result = await client.post(
        "/api/documents", files={"file": ("notes.md", b"The launch code is cedar.")}
    )
    document_id = result.json()["id"]
    assert (await wait_document(client, document_id))["status"] == "failed"
    assert svc.db.one("SELECT count(*) AS n FROM pages")["n"] == 1
    provider.failure = ""
    assert (await client.post(f"/api/documents/{document_id}/retry", json={})).status_code == 202
    assert (await wait_document(client, document_id))["status"] == "ready"
    assert (await client.post(f"/api/documents/{document_id}/retry", json={})).status_code == 409
    assert svc.db.one("SELECT count(*) AS n FROM chunks")["n"] == 1
    revised = await client.post(
        "/api/documents", files={"file": ("notes.md", b"The launch code is birch.")}
    )
    assert (await wait_document(client, revised.json()["id"]))["version"] == 2


async def test_restart_recovers_ingestion_and_preserves_history(tmp_path: Path) -> None:
    db = Database(tmp_path / "forge.sqlite3")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "doc").write_text("The launch code is cedar.")
    (uploads / "orphan").write_text("unfinished upload")
    db.execute(
        "INSERT INTO documents(id,name,hash,version,suffix,status) "
        "VALUES('doc','n','h',1,'.txt','embedding')"
    )
    db.execute("INSERT INTO pages VALUES('doc',1,'The launch code is cedar.',0)")
    db.execute("INSERT INTO runs(id,question,document_ids,status) VALUES('old','q','[]','running')")
    svc = Service(Settings(tmp_path), FakeOllama())
    await svc.start()
    await asyncio.gather(*list(svc.tasks.values()))
    assert svc.db.one("SELECT status FROM documents WHERE id='doc'")["status"] == "ready"
    assert svc.db.one("SELECT count(*) AS n FROM pages")["n"] == 1
    assert svc.db.one("SELECT count(*) AS n FROM chunks")["n"] == 1
    assert svc.db.one("SELECT status FROM runs WHERE id='old'")["status"] == "interrupted"
    assert not (uploads / "orphan").exists()
    await svc.close()
    other = Service(Settings(tmp_path), FakeOllama())
    await other.start()
    assert other.db.one("SELECT status FROM documents WHERE id='doc'")["status"] == "ready"
    assert other.db.one("SELECT status FROM runs WHERE id='old'")["status"] == "interrupted"
    await other.close()
