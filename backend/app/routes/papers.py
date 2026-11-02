from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from psycopg.errors import UniqueViolation
from pypdf import PdfReader

from ..access import require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import AttributeIn, ImportIn, PaperConceptIn, PaperIn, PaperPatch, ReadingStateIn
from ..services import embeddings, metadata

router = APIRouter(prefix="/papers", tags=["papers"])

# Every paper query returns these columns plus the caller's role and reading state.
PAPER_SELECT = """
    SELECT p.id, p.owner_id, u.name AS owner_name, p.title, p.authors, p.year, p.venue,
           p.doi, p.arxiv_id, p.abstract, p.summary, p.pdf_url, EXISTS (SELECT 1 FROM paper_files f WHERE f.paper_id = p.id) AS has_pdf,
           p.num_pages, p.created_at, p.updated_at,
           r.role,
           coalesce(s.status, 'to_read') AS status,
           coalesce(s.current_page, 1)   AS current_page,
           s.finished_at,
           (SELECT count(*) FROM highlights h WHERE h.paper_id = p.id) AS highlight_count,
           (SELECT coalesce(sum(extract(epoch FROM rs.ended_at - rs.started_at)), 0)::int
              FROM reading_sessions rs
             WHERE rs.paper_id = p.id AND rs.user_id = %(uid)s) AS seconds_read
    FROM papers p
    JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
    JOIN users u ON u.id = p.owner_id
    LEFT JOIN paper_reading_state s ON s.paper_id = p.id AND s.user_id = %(uid)s
"""


def fetch_paper(conn, user, paper_id) -> dict:
    row = conn.execute(PAPER_SELECT + " WHERE p.id = %(pid)s", {"uid": user["id"], "pid": paper_id}).fetchone()
    if row is None:
        raise HTTPException(404, "Paper not found")
    return row


def link_citations_by_doi(conn, paper_id) -> None:
    """Connect citations both ways using DOIs: references this paper lists that are in the
    database, and papers already in the database whose reference lists contain this paper's DOI.
    Only links papers with the same owner so nobody's graph is changed by someone else."""
    conn.execute(
        """
        INSERT INTO citations (citing_paper_id, cited_paper_id)
        SELECT %(pid)s, other.id
        FROM paper_reference_dois r
        JOIN papers me    ON me.id = %(pid)s
        JOIN papers other ON lower(other.doi) = r.doi AND other.owner_id = me.owner_id
        WHERE r.paper_id = %(pid)s AND other.id <> %(pid)s
        UNION
        SELECT other.id, %(pid)s
        FROM papers me
        JOIN paper_reference_dois r ON r.doi = lower(me.doi)
        JOIN papers other ON other.id = r.paper_id AND other.owner_id = me.owner_id
        WHERE me.id = %(pid)s AND me.doi IS NOT NULL AND other.id <> %(pid)s
        ON CONFLICT DO NOTHING
        """,
        {"pid": paper_id},
    )


def safe_embed(conn, paper: dict) -> None:
    """Embeddings are a bonus: never fail a save because the model hiccuped."""
    try:
        with conn.transaction():
            embeddings.store_paper_embedding(conn, paper)
    except Exception as e:  # noqa: BLE001
        print(f"embedding failed for paper {paper['id']}: {e}")


def save_pdf(conn, paper_id, data: bytes) -> None:
    try:
        num_pages = len(PdfReader(BytesIO(data)).pages)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "That file isn't a readable PDF")
    conn.execute(
        """
        INSERT INTO paper_files (paper_id, data) VALUES (%s, %s)
        ON CONFLICT (paper_id) DO UPDATE SET data = excluded.data, uploaded_at = now()
        """,
        (paper_id, data),
    )
    conn.execute("UPDATE papers SET num_pages = %s WHERE id = %s", (num_pages, paper_id))


# ---------------------------------------------------------------- CRUD

@router.get("")
def list_papers(status: str | None = None, user=Depends(current_user), conn=Depends(get_conn)):
    sql = PAPER_SELECT
    params = {"uid": user["id"]}
    if status:
        sql += " WHERE coalesce(s.status, 'to_read') = %(status)s"
        params["status"] = status
    return conn.execute(sql + " ORDER BY p.created_at DESC", params).fetchall()


@router.post("", status_code=201)
def create_paper(body: PaperIn, user=Depends(current_user), conn=Depends(get_conn)):
    try:
        row = conn.execute(
            """
            INSERT INTO papers (owner_id, title, authors, year, venue, doi, abstract, pdf_url)
            VALUES (%(uid)s, %(title)s, %(authors)s, %(year)s, %(venue)s, lower(%(doi)s::text), %(abstract)s, %(pdf_url)s)
            RETURNING id, title, abstract
            """,
            {"uid": user["id"], **body.model_dump()},
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, "You already have a paper with that DOI")
    safe_embed(conn, row)
    if body.doi:
        link_citations_by_doi(conn, row["id"])
    return fetch_paper(conn, user, row["id"])


@router.post("/import", status_code=201)
def import_paper(body: ImportIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Create a paper from a DOI or arXiv ID. arXiv PDFs are downloaded automatically."""
    kind, ident = metadata.parse_identifier(body.identifier)
    meta = metadata.fetch_arxiv(ident) if kind == "arxiv" else metadata.fetch_crossref(ident)

    existing = conn.execute(
        "SELECT id FROM papers WHERE owner_id = %s AND lower(doi) = %s", (user["id"], meta["doi"])
    ).fetchone()
    if existing:
        raise HTTPException(409, "This paper is already in your library")

    row = conn.execute(
        """
        INSERT INTO papers (owner_id, title, authors, year, venue, doi, arxiv_id, abstract, pdf_url)
        VALUES (%(uid)s, %(title)s, %(authors)s, %(year)s, %(venue)s, %(doi)s, %(arxiv_id)s, %(abstract)s, %(pdf_url)s)
        RETURNING id, title, abstract
        """,
        {"uid": user["id"], **meta},
    ).fetchone()

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO paper_reference_dois (paper_id, doi) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(row["id"], d) for d in meta["references"]],
        )
    link_citations_by_doi(conn, row["id"])
    safe_embed(conn, row)

    pdf_note = None
    if meta["pdf_url"]:
        try:
            save_pdf(conn, row["id"], metadata.download_pdf(meta["pdf_url"]))
        except HTTPException as e:
            pdf_note = e.detail   # metadata import still succeeds; user can upload the PDF by hand
    paper = fetch_paper(conn, user, row["id"])
    paper["pdf_note"] = pdf_note
    return paper


@router.get("/{paper_id}")
def get_paper(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    return fetch_paper(conn, user, paper_id)


@router.patch("/{paper_id}")
def update_paper(paper_id: UUID, body: PaperPatch, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("doi"):
        fields["doi"] = fields["doi"].strip().lower()
    if fields:
        # Column names come from the Pydantic model, never from user input, so this is safe.
        sets = ", ".join(f"{k} = %({k})s" for k in fields)
        row = conn.execute(
            f"UPDATE papers SET {sets} WHERE id = %(pid)s RETURNING id, title, abstract",
            {**fields, "pid": paper_id},
        ).fetchone()
        if {"title", "abstract"} & fields.keys():
            safe_embed(conn, row)
        if "doi" in fields:
            link_citations_by_doi(conn, paper_id)
    return fetch_paper(conn, user, paper_id)


@router.delete("/{paper_id}", status_code=204)
def delete_paper(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "owner")
    conn.execute("DELETE FROM papers WHERE id = %s", (paper_id,))   # paper_files row cascades


# ---------------------------------------------------------------- reading state

@router.put("/{paper_id}/state")
def set_reading_state(paper_id: UUID, body: ReadingStateIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    # UPSERT: insert the row the first time, update it afterwards.
    conn.execute(
        """
        INSERT INTO paper_reading_state (user_id, paper_id, status, current_page)
        VALUES (%(uid)s, %(pid)s, coalesce(%(status)s, 'to_read'), coalesce(%(page)s, 1))
        ON CONFLICT (user_id, paper_id) DO UPDATE
           SET status       = coalesce(%(status)s, paper_reading_state.status),
               current_page = coalesce(%(page)s,   paper_reading_state.current_page)
        """,
        {"uid": user["id"], "pid": paper_id, "status": body.status, "page": body.current_page},
    )
    return fetch_paper(conn, user, paper_id)


# ---------------------------------------------------------------- PDF

@router.post("/{paper_id}/pdf")
async def upload_pdf(paper_id: UUID, file: UploadFile = File(...), user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "PDF is larger than 50 MB")
    save_pdf(conn, paper_id, data)
    return fetch_paper(conn, user, paper_id)


@router.post("/{paper_id}/pdf/fetch")
def fetch_pdf_from_url(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    paper = fetch_paper(conn, user, paper_id)
    if not paper["pdf_url"]:
        raise HTTPException(400, "This paper has no PDF URL")
    save_pdf(conn, paper_id, metadata.download_pdf(paper["pdf_url"]))
    return fetch_paper(conn, user, paper_id)


@router.get("/{paper_id}/pdf")
def get_pdf(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    row = conn.execute("SELECT data FROM paper_files WHERE paper_id = %s", (paper_id,)).fetchone()
    if not row:
        raise HTTPException(404, "No PDF uploaded for this paper")
    return Response(bytes(row["data"]), media_type="application/pdf")


# ---------------------------------------------------------------- attributes (EAV)

@router.get("/{paper_id}/attributes")
def list_attributes(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    return conn.execute(
        "SELECT id, attr_name, attr_value FROM paper_attributes WHERE paper_id = %s ORDER BY attr_name",
        (paper_id,),
    ).fetchall()


@router.put("/{paper_id}/attributes")
def upsert_attribute(paper_id: UUID, body: AttributeIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    return conn.execute(
        """
        INSERT INTO paper_attributes (paper_id, attr_name, attr_value)
        VALUES (%s, lower(trim(%s)), %s)
        ON CONFLICT (paper_id, attr_name) DO UPDATE SET attr_value = EXCLUDED.attr_value
        RETURNING id, attr_name, attr_value
        """,
        (paper_id, body.attr_name, body.attr_value),
    ).fetchone()


@router.delete("/{paper_id}/attributes/{attr_id}", status_code=204)
def delete_attribute(paper_id: UUID, attr_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    conn.execute("DELETE FROM paper_attributes WHERE id = %s AND paper_id = %s", (attr_id, paper_id))


# ---------------------------------------------------------------- concepts on a paper

@router.get("/{paper_id}/concepts")
def list_paper_concepts(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    return conn.execute(
        """
        SELECT c.id, c.name, c.difficulty, pc.relation
        FROM paper_concepts pc JOIN concepts c ON c.id = pc.concept_id
        WHERE pc.paper_id = %s AND c.owner_id = %s
        ORDER BY pc.relation, c.name
        """,
        (paper_id, user["id"]),
    ).fetchall()


@router.get("/{paper_id}/learning-path")
def paper_learning_path(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Everything to learn BEFORE reading this paper, in learning order.

    Same recursive walk as a concept's prerequisite chain, but it starts from every concept
    the paper uses at once. Concepts the paper assumes are needed too (depth 0); concepts
    it introduces are what you'll learn FROM it, so they're left out of the list.
    """
    require_paper(conn, user, paper_id)
    params = {"pid": paper_id, "uid": user["id"]}
    paper_concepts = conn.execute(
        """
        SELECT c.id, c.name, c.description, c.difficulty, c.known, c.source, pc.relation
        FROM paper_concepts pc JOIN concepts c ON c.id = pc.concept_id AND c.owner_id = %(uid)s
        WHERE pc.paper_id = %(pid)s
        ORDER BY pc.relation DESC, c.name
        """,
        params,
    ).fetchall()
    learn_first = conn.execute(
        """
        WITH RECURSIVE
        used AS (
            SELECT pc.concept_id, pc.relation
            FROM paper_concepts pc JOIN concepts c ON c.id = pc.concept_id AND c.owner_id = %(uid)s
            WHERE pc.paper_id = %(pid)s
        ),
        chain (concept_id, depth, path) AS (
            SELECT cp.prerequisite_id, 1, ARRAY[cp.concept_id, cp.prerequisite_id]
            FROM concept_prerequisites cp JOIN used u ON u.concept_id = cp.concept_id
          UNION ALL
            SELECT cp.prerequisite_id, ch.depth + 1, ch.path || cp.prerequisite_id
            FROM concept_prerequisites cp JOIN chain ch ON cp.concept_id = ch.concept_id
            WHERE NOT cp.prerequisite_id = ANY (ch.path) AND ch.depth < 12
        ),
        needed AS (
            SELECT concept_id, depth FROM chain
          UNION ALL
            SELECT concept_id, 0 FROM used WHERE relation = 'assumes'
        )
        SELECT c.id, c.name, c.description, c.difficulty, c.known, c.source, max(n.depth) AS depth
        FROM needed n JOIN concepts c ON c.id = n.concept_id
        WHERE c.id NOT IN (SELECT concept_id FROM used WHERE relation = 'introduces')
        GROUP BY c.id
        ORDER BY depth DESC, c.name
        """,
        params,
    ).fetchall()

    ids = [c["id"] for c in paper_concepts] + [c["id"] for c in learn_first]
    # For each prerequisite: other papers you can open that teach it.
    teachers = {}
    for t in conn.execute(
        """
        SELECT pc.concept_id, p.id, p.title
        FROM paper_concepts pc
        JOIN papers p ON p.id = pc.paper_id
        JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
        WHERE pc.relation = 'introduces' AND pc.concept_id = ANY(%(ids)s) AND p.id <> %(pid)s
        ORDER BY p.title
        """,
        {**params, "ids": ids},
    ).fetchall():
        teachers.setdefault(t["concept_id"], []).append({"id": t["id"], "title": t["title"]})
    for c in learn_first:
        c["taught_by"] = teachers.get(c["id"], [])

    edges = conn.execute(
        """SELECT concept_id AS source, prerequisite_id AS target FROM concept_prerequisites
           WHERE concept_id = ANY(%s) AND prerequisite_id = ANY(%s)""",
        (ids, ids),
    ).fetchall()
    return {"paper_concepts": paper_concepts, "learn_first": learn_first, "edges": edges}


@router.put("/{paper_id}/concepts")
def set_paper_concept(paper_id: UUID, body: PaperConceptIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    owned = conn.execute(
        "SELECT 1 FROM concepts WHERE id = %s AND owner_id = %s", (body.concept_id, user["id"])
    ).fetchone()
    if not owned:
        raise HTTPException(404, "Concept not found")
    conn.execute(
        """
        INSERT INTO paper_concepts (paper_id, concept_id, relation) VALUES (%s, %s, %s)
        ON CONFLICT (paper_id, concept_id) DO UPDATE SET relation = EXCLUDED.relation
        """,
        (paper_id, body.concept_id, body.relation),
    )
    return list_paper_concepts(paper_id, user, conn)


@router.delete("/{paper_id}/concepts/{concept_id}", status_code=204)
def remove_paper_concept(paper_id: UUID, concept_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    conn.execute(
        """
        DELETE FROM paper_concepts pc USING concepts c
        WHERE c.id = pc.concept_id AND c.owner_id = %s AND pc.paper_id = %s AND pc.concept_id = %s
        """,
        (user["id"], paper_id, concept_id),
    )
