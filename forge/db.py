"""Small SQLite repository; every write is an explicit transaction."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, hash TEXT UNIQUE NOT NULL,
 version INTEGER NOT NULL, suffix TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, warnings TEXT NOT NULL DEFAULT '[]', extraction_ms REAL,
 embedding_digest TEXT, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS pages (
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 number INTEGER NOT NULL, text TEXT NOT NULL, ocr INTEGER NOT NULL,
 PRIMARY KEY(document_id,number)
);
CREATE TABLE IF NOT EXISTS chunks (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 page INTEGER NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL,
 embedding TEXT NOT NULL, UNIQUE(document_id,ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(id UNINDEXED, text);
CREATE TRIGGER IF NOT EXISTS chunk_insert AFTER INSERT ON chunks BEGIN
 INSERT INTO chunk_search(id,text) VALUES(new.id,new.text); END;
CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
 DELETE FROM chunk_search WHERE id=old.id; END;
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, question TEXT NOT NULL, document_ids TEXT NOT NULL,
 status TEXT NOT NULL, checkpoint TEXT NOT NULL DEFAULT 'queued',
 answer TEXT, citations TEXT NOT NULL DEFAULT '[]', evidence TEXT NOT NULL DEFAULT '[]',
 error TEXT, timings TEXT NOT NULL DEFAULT '{}', versions TEXT NOT NULL DEFAULT '{}',
 abstained INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS events (
 run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(run_id,seq)
);
PRAGMA user_version=1;
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported database version; restore a compatible release.")
            con.executescript(SCHEMA)
            con.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connection() as con:
            return [dict(row) for row in con.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self.connection() as con:
            con.execute(sql, args)

    def update_run(self, run_id: str, **fields: Any) -> bool:
        allowed = {
            "status",
            "checkpoint",
            "answer",
            "citations",
            "evidence",
            "error",
            "timings",
            "versions",
            "abstained",
        }
        if not fields or not fields.keys() <= allowed:
            raise ValueError("Unknown run field")
        # Terminal states cannot be overwritten by late workers or cancellation races.
        with self.connection() as con:
            result = con.execute(
                f"UPDATE runs SET {','.join(key + '=?' for key in fields)} "
                "WHERE id=? AND status IN ('queued','running')",
                (*fields.values(), run_id),
            )
            return bool(result.rowcount)

    def event(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self.connection() as con:
            if not con.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
                return
            con.execute(
                "INSERT INTO events VALUES(?,"
                "(SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?),?,?)",
                (run_id, run_id, kind, json.dumps(payload)),
            )


def decode_run(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ("document_ids", "citations", "evidence", "timings", "versions"):
        result[key] = json.loads(result[key])
    result["abstained"] = bool(result["abstained"])
    return result
