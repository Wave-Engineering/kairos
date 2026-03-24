"""Embedding pipeline — embeds contract chunks into sqlite-vec for semantic search."""

from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

import yaml

from kairos.chunker import chunk_contract
from kairos.models import Chunk, Contract


def _serialize_f32(vector: list[float]) -> bytes:
    """Serialize a list of floats into a compact binary format for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def _init_db(conn: sqlite3.Connection) -> None:
    """Drop and recreate the chunks_vec and chunks_meta tables.

    This ensures each embed run fully replaces previous data (idempotent).
    """
    conn.execute("DROP TABLE IF EXISTS chunks_vec")
    conn.execute("DROP TABLE IF EXISTS chunks_meta")
    conn.execute("CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[384])")
    conn.execute(
        "CREATE TABLE chunks_meta("
        "id INTEGER PRIMARY KEY, "
        "repo_name TEXT, "
        "section TEXT, "
        "field_path TEXT, "
        "text TEXT"
        ")"
    )


def embed_contracts(
    contracts_dir: Path,
    db_path: Path,
    model_name: str = "all-MiniLM-L6-v2",
) -> tuple[int, int]:
    """Read YAML contracts, chunk them, embed with sentence-transformers, store in sqlite-vec.

    Args:
        contracts_dir: Directory containing contract YAML files.
        db_path: Path to the sqlite database file (created if it doesn't exist).
        model_name: Name of the sentence-transformers model to use.

    Returns:
        A tuple of (total_chunks, total_contracts) embedded.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    # Collect all chunks from all valid contracts.
    all_chunks: list[Chunk] = []
    contract_count = 0
    skipped = 0

    for yaml_path in sorted(contracts_dir.glob("*.yaml")):
        try:
            contract = Contract.from_yaml(yaml_path)
        except (yaml.YAMLError, KeyError, FileNotFoundError) as exc:
            print(
                f"Warning: skipping invalid contract {yaml_path.name}: {exc}",
                file=sys.stderr,
            )
            skipped += 1
            continue

        chunks = chunk_contract(contract)
        all_chunks.extend(chunks)
        contract_count += 1

    if not all_chunks:
        print("No chunks to embed.")
        return 0, contract_count

    # Batch-encode all chunk texts.
    texts = [c.text for c in all_chunks]
    embeddings = model.encode(texts)

    # Open (or create) the sqlite-vec database and load the extension.
    import sqlite_vec

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    _init_db(conn)

    # Insert metadata and vectors with matching rowids.
    for i, (chunk, embedding) in enumerate(zip(all_chunks, embeddings), start=1):
        conn.execute(
            "INSERT INTO chunks_meta(id, repo_name, section, field_path, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (i, chunk.repo_name, chunk.section, chunk.field_path, chunk.text),
        )
        conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
            (i, _serialize_f32(embedding.tolist())),
        )

    conn.commit()
    conn.close()

    return len(all_chunks), contract_count


def search(
    query: str,
    model: object,
    db_path: Path,
    top_k: int = 10,
) -> list[tuple[Chunk, float]]:
    """Search the embedding database for chunks semantically similar to the query.

    Args:
        query: The search query string.
        model: A loaded SentenceTransformer model instance.
        db_path: Path to the sqlite-vec database.
        top_k: Maximum number of results to return.

    Returns:
        A list of (Chunk, distance) tuples, ordered by ascending distance
        (lower distance = more similar).
    """
    import sqlite_vec

    # Encode the query.
    query_embedding = model.encode([query])[0]

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Query sqlite-vec for nearest neighbours.
    rows = conn.execute(
        "SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (_serialize_f32(query_embedding.tolist()), top_k),
    ).fetchall()

    results: list[tuple[Chunk, float]] = []
    for rowid, distance in rows:
        meta = conn.execute(
            "SELECT repo_name, section, field_path, text FROM chunks_meta WHERE id = ?",
            (rowid,),
        ).fetchone()

        if meta:
            chunk = Chunk(
                text=meta[3],
                repo_name=meta[0],
                section=meta[1],
                field_path=meta[2],
            )
            results.append((chunk, distance))

    conn.close()
    return results
