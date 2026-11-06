import json

import httpx
import pytest

from forge.config import CHAT_MODEL, EMBED_MODEL
from forge.ollama import ModelError, Ollama


async def test_inventory_embeddings_and_allowlist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": CHAT_MODEL, "digest": "chat"},
                        {"name": EMBED_MODEL + ":latest", "digest": "embed"},
                    ]
                },
            )
        payload = json.loads(request.content)
        assert payload["model"] == EMBED_MODEL
        assert payload["input"] == ["search_query: hello"]
        assert payload["truncate"] is False
        return httpx.Response(200, json={"embeddings": [[1, 2, 3]]})

    provider = Ollama("http://localhost", httpx.MockTransport(handler))
    assert (await provider.models())[CHAT_MODEL] == "chat"
    assert await provider.embed(["hello"], query=True) == [[1, 2, 3]]
    with pytest.raises(ModelError, match="allowlisted"):
        async for _ in provider.generate("q", [], "not-approved"):
            pass
    await provider.close()


async def test_transient_retry_budget() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    provider = Ollama("http://localhost", httpx.MockTransport(handler))
    with pytest.raises(ModelError, match="unavailable"):
        await provider.models()
    assert attempts == 3
    await provider.close()


@pytest.mark.parametrize("data", [{"embeddings": []}, {"embeddings": [["NaN"]]}, {"oops": []}])
async def test_embedding_boundary(data: dict) -> None:
    provider = Ollama(
        "http://localhost", httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    )
    with pytest.raises(ModelError, match="invalid embeddings"):
        await provider.embed(["text"])
    await provider.close()


@pytest.mark.parametrize(
    "body",
    [
        '{"message":{"content":"partial"},"done":false}\n',
        "not json\n",
        '{"error":"private provider details"}\n',
        '{"done":true,"done_reason":"length"}\n',
    ],
)
async def test_stream_failures_are_not_answers(body: str) -> None:
    provider = Ollama(
        "http://localhost",
        httpx.MockTransport(
            lambda _: httpx.Response(200, text=body),
        ),
    )
    with pytest.raises(ModelError):
        async for _ in provider.generate("q", []):
            pass
    await provider.close()


async def test_stream_success_and_transient_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429)
        data = json.loads(request.content)
        assert data["format"]["type"] == "object"
        assert data["think"] is False
        assert "tools" not in data
        return httpx.Response(200, text='{"message":{"content":"hello"}}\n{"done":true}\n')

    provider = Ollama("http://localhost", httpx.MockTransport(handler))
    pieces = [piece async for piece in provider.generate("q", [])]
    assert pieces == ["hello"]
    assert attempts == 3
    await provider.close()


async def test_missing_models_and_nontransient_failure() -> None:
    provider = Ollama(
        "http://localhost",
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"models": []}),
        ),
    )
    with pytest.raises(ModelError, match="ollama pull"):
        await provider.models()
    await provider.close()
    attempts = 0

    def denied(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(403)

    provider = Ollama("http://localhost", httpx.MockTransport(denied))
    with pytest.raises(ModelError, match="403"):
        await provider.models()
    assert attempts == 1
    await provider.close()
