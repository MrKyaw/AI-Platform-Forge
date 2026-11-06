import asyncio
import json
import math
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from forge.app import create_app
from forge.config import CHAT_MODEL, EMBED_MODEL, Settings
from forge.ollama import ModelError, Ollama


class FakeOllama(Ollama):
    """Deterministic boundary fake; it establishes application behavior, never model quality."""

    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:11435")
        self.delay = 0.0
        self.failure = ""
        self.raw: str | None = None
        self.embedding_calls = 0

    async def models(self) -> dict[str, str]:
        if self.failure == "models":
            raise ModelError("Missing model. Run: ollama pull qwen3:4b")
        return {CHAT_MODEL: "chat-test-digest", EMBED_MODEL: "embed-test-digest"}

    async def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        self.embedding_calls += 1
        if self.failure == "embed":
            raise ModelError("Embedding unavailable")
        result = []
        for text in texts:
            vector = [0.0] * 32
            for word in re.findall(r"\w+", text.lower()):
                vector[sum(word.encode()) % 32] += 1
            norm = math.sqrt(sum(x * x for x in vector)) or 1
            result.append([x / norm for x in vector])
        return result

    async def generate(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        model: str = CHAT_MODEL,
    ) -> AsyncIterator[str]:
        await asyncio.sleep(self.delay)
        if self.failure == "generate":
            yield '{"answer":"unfinished'
            raise ModelError("The model stream was interrupted. The answer is incomplete.")
        raw = self.raw or json.dumps(
            {
                "answer": "The launch code is cedar.",
                "citations": [{"id": evidence[0]["id"], "quote": evidence[0]["text"][:100]}],
                "abstained": False,
            }
        )
        for offset in range(0, len(raw), 30):
            yield raw[offset : offset + 30]
            await asyncio.sleep(0)


@pytest.fixture
async def workspace(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, Any, FakeOllama]]:
    provider = FakeOllama()
    app = create_app(Settings(tmp_path), provider)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, app.state.service, provider


async def wait_document(client: httpx.AsyncClient, document_id: str) -> dict[str, Any]:
    for _ in range(300):
        row = (await client.get(f"/api/documents/{document_id}")).json()
        if row["status"] in {"ready", "failed"}:
            return row
        await asyncio.sleep(0.02)
    raise AssertionError("document did not finish")


async def upload_ready(client: httpx.AsyncClient, name: str = "notes.md") -> str:
    response = await client.post(
        "/api/documents",
        files={"file": (name, b"# Launch\nThe launch code is cedar.")},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    assert (await wait_document(client, document_id))["status"] == "ready"
    return document_id


async def wait_run(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    for _ in range(300):
        row = (await client.get(f"/api/runs/{run_id}")).json()
        if row["status"] not in {"queued", "running"}:
            return row
        await asyncio.sleep(0.01)
    raise AssertionError("run did not finish")
