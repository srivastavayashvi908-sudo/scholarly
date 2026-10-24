"""Database connection pool and a tiny migration runner.

All queries in this project are plain SQL run through psycopg, so you can see
(and explain) exactly what hits the database.
"""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

pool = ConnectionPool(DATABASE_URL, kwargs={"row_factory": dict_row}, open=False)


def run_migrations() -> None:
    """Apply every migrations/*.sql file that hasn't been applied yet, in name order."""
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )""")
        # Only one process may migrate at a time (uvicorn --reload can start twice).
        conn.execute("SELECT pg_advisory_lock(42)")
        try:
            done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
                print(f"applied migration {path.name}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(42)")


def get_conn():
    """FastAPI dependency: one connection per request, committed if the request succeeds."""
    with pool.connection() as conn:
        yield conn


def vector_literal(values) -> str:
    """Format a Python list as pgvector's text form, e.g. '[0.1,0.2]' (used with ::vector)."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"
