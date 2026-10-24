"""Local text embeddings with fastembed (no API key, runs on CPU)."""
import threading

from ..config import EMBEDDING_MODEL
from ..db import vector_literal

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(EMBEDDING_MODEL)
        return _model


def warm_up() -> None:
    _get_model()


def embed_passage(text: str) -> str:
    """Embed a document (abstract, highlight...). Returns a pgvector literal."""
    vec = next(iter(_get_model().passage_embed([text])))
    return vector_literal(vec)


def embed_query(text: str) -> str:
    """Embed a search question. bge models use a slightly different prompt for queries."""
    vec = next(iter(_get_model().query_embed([text])))
    return vector_literal(vec)


def paper_text(paper: dict) -> str:
    parts = [paper.get("title") or "", paper.get("abstract") or paper.get("summary") or ""]
    return "\n\n".join(p for p in parts if p)


def store_paper_embedding(conn, paper: dict) -> None:
    conn.execute(
        """
        INSERT INTO paper_embeddings (paper_id, embedding) VALUES (%s, %s::vector)
        ON CONFLICT (paper_id) DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = now()
        """,
        (paper["id"], embed_passage(paper_text(paper))),
    )


def store_highlight_embedding(conn, highlight: dict) -> None:
    conn.execute(
        """
        INSERT INTO highlight_embeddings (highlight_id, embedding) VALUES (%s, %s::vector)
        ON CONFLICT (highlight_id) DO UPDATE SET embedding = EXCLUDED.embedding
        """,
        (highlight["id"], embed_passage(highlight["quote"])),
    )


def store_concept_embedding(conn, concept: dict) -> None:
    text = concept["name"] + (". " + concept["description"] if concept.get("description") else "")
    conn.execute(
        """
        INSERT INTO concept_embeddings (concept_id, embedding) VALUES (%s, %s::vector)
        ON CONFLICT (concept_id) DO UPDATE SET embedding = EXCLUDED.embedding
        """,
        (concept["id"], embed_passage(text)),
    )
