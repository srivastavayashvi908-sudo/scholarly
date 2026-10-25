from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pypdf import PdfReader

from ..access import require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import AskIn
from ..services import embeddings, llm

router = APIRouter(tags=["ai"])


@router.post("/papers/{paper_id}/embed")
def embed_paper(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """(Re)compute a paper's embedding. Normally this happens automatically on save."""
    require_paper(conn, user, paper_id)
    paper = conn.execute("SELECT id, title, abstract, summary FROM papers WHERE id = %s", (paper_id,)).fetchone()
    embeddings.store_paper_embedding(conn, paper)
    return {"ok": True}


@router.get("/papers/{paper_id}/similar")
def similar_papers(paper_id: UUID, limit: int = 5, user=Depends(current_user), conn=Depends(get_conn)):
    """Nearest neighbours by cosine distance (<=>). similarity = 1 - distance."""
    require_paper(conn, user, paper_id)
    return conn.execute(
        """
        SELECT p.id, p.title, p.authors, p.year,
               round((1 - (e.embedding <=> me.embedding))::numeric, 3) AS similarity
        FROM paper_embeddings me
        JOIN paper_embeddings e ON e.paper_id <> me.paper_id
        JOIN papers p ON p.id = e.paper_id
        JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
        WHERE me.paper_id = %(pid)s
        ORDER BY e.embedding <=> me.embedding
        LIMIT %(lim)s
        """,
        {"pid": paper_id, "uid": user["id"], "lim": min(limit, 20)},
    ).fetchall()


def pdf_text(data: bytes, max_chars: int = 15000) -> str:
    reader = PdfReader(BytesIO(data))
    out = []
    for page in reader.pages[:6]:
        out.append(page.extract_text() or "")
        if sum(map(len, out)) > max_chars:
            break
    return "\n".join(out)[:max_chars]


@router.post("/papers/{paper_id}/summarize")
def summarize(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    paper = conn.execute("SELECT * FROM papers WHERE id = %s", (paper_id,)).fetchone()
    source = paper["abstract"] or ""
    pdf = conn.execute("SELECT data FROM paper_files WHERE paper_id = %s", (paper_id,)).fetchone()
    if pdf:
        try:
            source = (source + "\n\n" + pdf_text(bytes(pdf["data"]))).strip()
        except Exception:  # noqa: BLE001
            pass
    if not source:
        raise HTTPException(400, "Add an abstract or upload the PDF first; there's nothing to summarize")
    summary = llm.chat(
        "You summarize research papers for a student. Write 3-5 short bullet points covering: "
        "the problem, the method, the key result, and one limitation if visible. Plain text, "
        "each bullet starting with '- '. No markdown (no ** or #). No preamble.",
        f"Title: {paper['title']}\n\n{source}",
    )
    conn.execute("UPDATE papers SET summary = %s WHERE id = %s", (summary, paper_id))
    return {"summary": summary}


@router.post("/ask")
def ask_library(body: AskIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Retrieval-augmented question answering over your own library.

    1. Embed the question.
    2. Find the closest highlights and paper abstracts with pgvector (<=> cosine distance).
    3. Hand only those snippets to the LLM and ask it to answer citing them as [1], [2]...
    """
    q = embeddings.embed_query(body.question)
    sources = conn.execute(
        """
        WITH visible AS (SELECT paper_id FROM v_paper_role WHERE user_id = %(uid)s)
        (
            SELECT 'highlight' AS kind, h.id, h.paper_id, p.title AS paper_title, h.page,
                   h.quote AS text, e.embedding <=> %(q)s::vector AS distance
            FROM highlight_embeddings e
            JOIN highlights h ON h.id = e.highlight_id
            JOIN papers p ON p.id = h.paper_id
            WHERE h.paper_id IN (SELECT paper_id FROM visible)
            ORDER BY e.embedding <=> %(q)s::vector
            LIMIT 8
        )
        UNION ALL
        (
            SELECT 'paper', p.id, p.id, p.title, NULL,
                   coalesce(p.abstract, p.summary, p.title), e.embedding <=> %(q)s::vector
            FROM paper_embeddings e
            JOIN papers p ON p.id = e.paper_id
            WHERE p.id IN (SELECT paper_id FROM visible)
            ORDER BY e.embedding <=> %(q)s::vector
            LIMIT 5
        )
        ORDER BY distance
        LIMIT 10
        """,
        {"uid": user["id"], "q": q},
    ).fetchall()
    if not sources:
        return {"answer": "Your library is empty, so there's nothing to answer from yet.", "sources": []}

    context = "\n\n".join(
        f"[{i}] ({s['kind']} from \"{s['paper_title']}\"{', p.' + str(s['page']) if s['page'] else ''})\n{s['text'][:1500]}"
        for i, s in enumerate(sources, 1)
    )
    answer = llm.chat(
        "You answer questions using ONLY the numbered snippets from the user's research library. "
        "Cite snippets inline like [1] or [2][3]. If the snippets don't contain the answer, say so "
        "plainly instead of guessing. Be concise. Plain text only, no markdown (no ** or #).",
        f"Snippets:\n{context}\n\nQuestion: {body.question}",
        max_tokens=3000,
    )
    for i, s in enumerate(sources, 1):
        s["n"] = i
        s["similarity"] = round(1 - s.pop("distance"), 3)
    return {"answer": answer, "sources": sources}
