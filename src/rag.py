import os
import sqlite3
import struct
from pathlib import Path

import sqlite_vec

DB_PATH = os.environ.get("DB_PATH", "data/db/vectors.db")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "768"))


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{EMBED_DIM}])"
    )
    conn.commit()
    conn.close()


def _serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split on paragraph/sentence boundaries where possible, falling back to a hard cut."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            boundary = text.rfind("\n\n", start, end)
            if boundary == -1:
                boundary = text.rfind(". ", start, end)
            if boundary != -1 and boundary > start + chunk_size // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end - overlap > start else end
    return chunks


def add_chunk(source: str, chunk_index: int, text: str, embedding: list[float]) -> None:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO chunks (source, chunk_index, text) VALUES (?, ?, ?)",
        (source, chunk_index, text),
    )
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
        (rowid, _serialize(embedding)),
    )
    conn.commit()
    conn.close()


def search(query_embedding: list[float], k: int = 4) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT c.source, c.chunk_index, c.text, v.distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (_serialize(query_embedding), k),
    ).fetchall()
    conn.close()
    return [
        {"source": r[0], "chunk_index": r[1], "text": r[2], "distance": r[3]}
        for r in rows
    ]


def list_sources() -> list[str]:
    conn = _connect()
    rows = conn.execute("SELECT DISTINCT source FROM chunks ORDER BY source").fetchall()
    conn.close()
    return [r[0] for r in rows]


def delete_source(source: str) -> None:
    conn = _connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE source = ?", (source,)).fetchall()]
    conn.executemany("DELETE FROM vec_chunks WHERE rowid = ?", [(i,) for i in ids])
    conn.execute("DELETE FROM chunks WHERE source = ?", (source,))
    conn.commit()
    conn.close()
