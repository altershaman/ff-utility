import os
import sqlite3
import sys

import sqlite_vec


def db_path(git_dir: str) -> str:
    return os.path.join(git_dir, 'bb', 'bb.db')


def get_connection(git_dir: str) -> sqlite3.Connection:
    path = db_path(git_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    _ensure_concepts_table(conn)
    return conn


def _ensure_concepts_table(conn: sqlite3.Connection) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS concepts (
            uuid                  TEXT PRIMARY KEY,
            title                 TEXT,
            ref_sha               TEXT,
            blob_sha              TEXT,
            version               INTEGER,
            updated_at            TEXT,
            source_uuid           TEXT,
            source_version        INTEGER,
            retired               INTEGER DEFAULT 0,
            absorbed_into         TEXT,
            absorbed_into_version INTEGER
        )
    ''')
    # migrate existing DBs
    cols = {row[1] for row in conn.execute('PRAGMA table_info(concepts)')}
    for col, definition in [
        ('source_uuid',           'TEXT'),
        ('source_version',        'INTEGER'),
        ('retired',               'INTEGER DEFAULT 0'),
        ('absorbed_into',         'TEXT'),
        ('absorbed_into_version', 'INTEGER'),
    ]:
        if col not in cols:
            conn.execute(f'ALTER TABLE concepts ADD COLUMN {col} {definition}')
    conn.commit()


def ensure_vector_tables(conn: sqlite3.Connection, dim: int) -> None:
    conn.execute(f'''
        CREATE VIRTUAL TABLE IF NOT EXISTS concept_embeddings USING vec0(
            uuid      TEXT,
            embedding float[{dim}]
        )
    ''')
    conn.commit()


def upsert_concept(
    conn: sqlite3.Connection,
    uuid: str,
    title: str,
    ref_sha: str,
    blob_sha: str,
    version: int,
    updated_at: str,
    source_uuid: str | None = None,
    source_version: int | None = None,
) -> None:
    conn.execute('''
        INSERT INTO concepts (uuid, title, ref_sha, blob_sha, version, updated_at, source_uuid, source_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(uuid) DO UPDATE SET
            title = excluded.title,
            ref_sha = excluded.ref_sha,
            blob_sha = excluded.blob_sha,
            version = excluded.version,
            updated_at = excluded.updated_at,
            source_uuid = excluded.source_uuid,
            source_version = excluded.source_version
    ''', (uuid, title, ref_sha, blob_sha, version, updated_at, source_uuid, source_version))
    conn.commit()


def get_branches_from(conn: sqlite3.Connection, uuid: str) -> list[dict]:
    """Return all concepts that directly branched from the given UUID."""
    rows = conn.execute(
        'SELECT uuid, source_version FROM concepts WHERE source_uuid = ? ORDER BY source_version',
        (uuid,)
    ).fetchall()
    return [dict(r) for r in rows]


def retire_concept(
    conn: sqlite3.Connection,
    uuid: str,
    absorbed_into: str,
    absorbed_into_version: int,
) -> None:
    conn.execute('''
        UPDATE concepts
        SET retired = 1, absorbed_into = ?, absorbed_into_version = ?
        WHERE uuid = ?
    ''', (absorbed_into, absorbed_into_version, uuid))
    conn.commit()


def upsert_embedding(
    conn: sqlite3.Connection,
    uuid: str,
    embedding: list[float],
) -> None:
    conn.execute('DELETE FROM concept_embeddings WHERE uuid = ?', (uuid,))
    conn.execute(
        'INSERT INTO concept_embeddings (uuid, embedding) VALUES (?, ?)',
        (uuid, sqlite_vec.serialize_float32(embedding)),
    )
    conn.commit()


def search_concepts(
    conn: sqlite3.Connection,
    embedding: list[float],
    limit: int = 10,
) -> list[dict]:
    rows = conn.execute('''
        SELECT c.uuid, c.title, c.blob_sha,
               e.distance
        FROM concept_embeddings e
        JOIN concepts c ON c.uuid = e.uuid
        WHERE embedding MATCH ?
          AND k = ?
        ORDER BY e.distance
    ''', (sqlite_vec.serialize_float32(embedding), limit)).fetchall()
    return [dict(r) for r in rows]


def get_concept_row(conn: sqlite3.Connection, uuid: str) -> dict | None:
    row = conn.execute(
        'SELECT * FROM concepts WHERE uuid = ?', (uuid,)
    ).fetchone()
    return dict(row) if row else None


def vector_tables_exist(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='concept_embeddings'"
    ).fetchone()
    return row is not None
