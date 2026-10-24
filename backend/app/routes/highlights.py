from uuid import UUID

from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb

from ..access import require_highlight, require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import HighlightIn, HighlightPatch
from ..services import embeddings

router = APIRouter(tags=["highlights"])

HIGHLIGHT_SELECT = """
    SELECT h.id, h.paper_id, h.user_id, u.name AS user_name, h.quote, h.tag, h.color,
           h.page, h.position, h.created_at,
           (SELECT count(*) FROM highlight_comments c WHERE c.highlight_id = h.id) AS comment_count
    FROM highlights h JOIN users u ON u.id = h.user_id
"""


@router.get("/papers/{paper_id}/highlights")
def list_highlights(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    return conn.execute(
        HIGHLIGHT_SELECT + " WHERE h.paper_id = %s ORDER BY h.page NULLS LAST, h.created_at",
        (paper_id,),
    ).fetchall()


@router.post("/papers/{paper_id}/highlights", status_code=201)
def create_highlight(paper_id: UUID, body: HighlightIn, user=Depends(current_user), conn=Depends(get_conn)):
    # Viewers may highlight too: a highlight belongs to the person who made it.
    require_paper(conn, user, paper_id)
    h = conn.execute(
        """
        INSERT INTO highlights (paper_id, user_id, quote, tag, color, page, position)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, quote
        """,
        (
            paper_id, user["id"], body.quote.strip(), body.tag, body.color, body.page,
            Jsonb(body.position.model_dump()) if body.position else None,
        ),
    ).fetchone()
    try:
        with conn.transaction():
            embeddings.store_highlight_embedding(conn, h)
    except Exception as e:  # noqa: BLE001
        print(f"embedding failed for highlight {h['id']}: {e}")
    return conn.execute(HIGHLIGHT_SELECT + " WHERE h.id = %s", (h["id"],)).fetchone()


@router.patch("/highlights/{highlight_id}")
def update_highlight(highlight_id: UUID, body: HighlightPatch, user=Depends(current_user), conn=Depends(get_conn)):
    require_highlight(conn, user, highlight_id, own=True)
    fields = body.model_dump(exclude_unset=True)
    if fields:
        sets = ", ".join(f"{k} = %({k})s" for k in fields)
        conn.execute(f"UPDATE highlights SET {sets} WHERE id = %(hid)s", {**fields, "hid": highlight_id})
    return conn.execute(HIGHLIGHT_SELECT + " WHERE h.id = %s", (highlight_id,)).fetchone()


@router.delete("/highlights/{highlight_id}", status_code=204)
def delete_highlight(highlight_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_highlight(conn, user, highlight_id, own=True)
    conn.execute("DELETE FROM highlights WHERE id = %s", (highlight_id,))
