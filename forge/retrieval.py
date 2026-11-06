"""Lexical and vector rankings fused without comparing incompatible score scales."""

import json
import math
import re
from typing import Any

from forge.db import Database


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding dimensions do not match; reindex the document.")
    denominator = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0


def retrieve(
    db: Database,
    question: str,
    vector: list[float],
    document_ids: list[str],
    digest: str,
) -> list[dict[str, Any]]:
    args: tuple[Any, ...] = ()
    where = "d.status='ready'"
    if document_ids:
        where += f" AND d.id IN ({','.join('?' for _ in document_ids)})"
        args = tuple(document_ids)
    rows = db.rows(
        "SELECT c.*,d.name,d.version,d.embedding_digest FROM chunks c "
        f"JOIN documents d ON d.id=c.document_id WHERE {where}",
        args,
    )
    if any(row["embedding_digest"] != digest for row in rows):
        raise ValueError("The embedding model changed; reindex documents before asking questions.")
    tokens = re.findall(r"\w+", question, flags=re.UNICODE)[:40]
    lexical: list[dict[str, Any]] = []
    if tokens:
        expression = " OR ".join('"' + token + '"' for token in tokens)
        lexical = db.rows(
            "SELECT chunk_search.id FROM chunk_search "
            "JOIN chunks c ON c.id=chunk_search.id JOIN documents d ON d.id=c.document_id "
            f"WHERE chunk_search MATCH ? AND {where} ORDER BY bm25(chunk_search) LIMIT 50",
            (expression, *args),
        )
    ranked = sorted(
        rows,
        key=lambda row: (-cosine(vector, json.loads(row["embedding"])), row["id"]),
    )[:50]
    scores: dict[str, float] = {}
    for ranking in (lexical, ranked):
        for rank, row in enumerate(ranking, 1):
            scores[row["id"]] = scores.get(row["id"], 0) + 1 / (60 + rank)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda row: (-scores.get(row["id"], 0), row["id"])):
        if row["text"] in seen or row["id"] not in scores:
            continue
        seen.add(row["text"])
        result.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"embedding", "embedding_digest", "ordinal"}
            }
            | {"score": scores[row["id"]]}
        )
        if len(result) == 5:
            break
    return result
