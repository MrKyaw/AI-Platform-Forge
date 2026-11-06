import json
from pathlib import Path

import pytest

from forge.config import Settings
from forge.db import Database
from forge.extract import chunk_text, extract
from forge.ollama import ModelError, validate_answer
from forge.retrieval import cosine, retrieve


def test_heading_chunks_and_overlap() -> None:
    words = [str(i) for i in range(1000)]
    chunks = chunk_text("# First\n" + " ".join(words) + "\n# Second\nNew section")
    assert len(chunks[0].split()) == 500
    assert chunks[0].split()[-75:] == chunks[1].split()[:75]
    assert chunks[-1] == "# Second New section"
    assert chunk_text("") == []
    with pytest.raises(ValueError):
        chunk_text("bad", 10, 10)


@pytest.mark.parametrize("text", ["", "\x00binary", "a" * 2_000_001])
def test_reject_invalid_text(tmp_path: Path, text: str) -> None:
    file = tmp_path / "test.txt"
    file.write_text(text)
    with pytest.raises(ValueError):
        extract(file, ".txt")


def test_text_encoding_and_extensions(tmp_path: Path) -> None:
    file = tmp_path / "notes.txt"
    file.write_bytes(b"\xef\xbb\xbfCedar launch")
    assert extract(file, ".txt")["pages"][0]["text"] == "Cedar launch"
    file.write_bytes(b"\xff\xfe")
    with pytest.raises(UnicodeError):
        extract(file, ".txt")
    with pytest.raises(ValueError):
        extract(file, ".exe")


def test_cosine() -> None:
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([0, 0], [1, 0]) == 0
    with pytest.raises(ValueError):
        cosine([1], [1, 2])


def test_hybrid_filter_dedup_and_model_identity(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    for document_id, text in (("a", "Cedar launch"), ("b", "Cedar launch"), ("c", "Tides")):
        db.execute(
            "INSERT INTO documents(id,name,hash,version,suffix,status,embedding_digest) "
            "VALUES(?,?,?,1,'.txt','ready','digest')",
            (document_id, document_id, document_id),
        )
        db.execute(
            "INSERT INTO chunks VALUES(?,?,1,0,?,?)",
            (
                document_id + ":0",
                document_id,
                text,
                json.dumps([1, 0]),
            ),
        )
    result = retrieve(db, '"Cedar" OR (*', [1, 0], [], "digest")
    assert len(result) == 2
    assert result[0]["text"] == "Cedar launch"
    assert [r["document_id"] for r in retrieve(db, "Cedar", [1, 0], ["c"], "digest")] == ["c"]
    with pytest.raises(ValueError, match="changed"):
        retrieve(db, "Cedar", [1, 0], [], "new-digest")
    db.execute("DELETE FROM documents WHERE id='a'")
    assert db.one("SELECT count(*) AS n FROM chunk_search WHERE id='a:0'")["n"] == 0


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"answer":"Cedar","citations":[],"abstained":false}',
        '{"answer":"Cedar","citations":[{"id":"unknown","quote":"Cedar"}],"abstained":false}',
        '{"answer":"Cedar","citations":[{"id":"a","quote":"Not in source"}],"abstained":false}',
        '{"answer":"Cedar","citations":[],"abstained":false,"tool":"shell"}',
    ],
)
def test_reject_unsupported_answers(raw: str) -> None:
    with pytest.raises(ModelError):
        validate_answer(raw, [{"id": "a", "text": "Cedar launch"}])


def test_accept_answer_and_abstention() -> None:
    evidence = [{"id": "a", "text": "Cedar launch"}]
    answer = validate_answer(
        json.dumps(
            {
                "answer": "Cedar",
                "citations": [{"id": "a", "quote": "Cedar"}],
                "abstained": False,
            }
        ),
        evidence,
    )
    assert answer.answer == "Cedar"
    assert validate_answer(
        json.dumps(
            {
                "answer": "Not in the documents.",
                "citations": [],
                "abstained": True,
            }
        ),
        evidence,
    ).abstained


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.example",
        "http://192.168.1.1",
        "http://user:pass@localhost",
        "http://localhost/remote",
        "http://localhost?remote=1",
    ],
)
def test_no_remote_model_endpoints(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValueError):
        Settings(tmp_path, url)


def test_terminal_state_is_immutable(tmp_path: Path) -> None:
    db = Database(tmp_path / "state.db")
    db.execute("INSERT INTO runs(id,question,document_ids,status) VALUES('r','q','[]','queued')")
    assert db.update_run("r", status="cancelled")
    assert not db.update_run("r", status="completed", answer="late response")
    assert db.one("SELECT answer FROM runs WHERE id='r'")["answer"] is None
    with pytest.raises(ValueError):
        db.update_run("r", fake="invalid")
