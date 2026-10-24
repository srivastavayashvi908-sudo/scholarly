from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..access import require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import CitationIn

router = APIRouter(tags=["citations"])


@router.get("/papers/{paper_id}/citations")
def paper_citations(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Direct citations in both directions, limited to papers the user can see."""
    require_paper(conn, user, paper_id)
    params = {"pid": paper_id, "uid": user["id"]}
    cites = conn.execute(
        """
        SELECT p.id, p.title, p.year FROM citations c
        JOIN papers p ON p.id = c.cited_paper_id
        JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
        WHERE c.citing_paper_id = %(pid)s ORDER BY p.year NULLS LAST
        """,
        params,
    ).fetchall()
    cited_by = conn.execute(
        """
        SELECT p.id, p.title, p.year FROM citations c
        JOIN papers p ON p.id = c.citing_paper_id
        JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
        WHERE c.cited_paper_id = %(pid)s ORDER BY p.year NULLS LAST
        """,
        params,
    ).fetchall()
    return {"cites": cites, "cited_by": cited_by}


@router.post("/papers/{paper_id}/citations", status_code=201)
def add_citation(paper_id: UUID, body: CitationIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    require_paper(conn, user, body.cited_paper_id)
    if paper_id == body.cited_paper_id:
        raise HTTPException(400, "A paper can't cite itself")
    conn.execute(
        "INSERT INTO citations (citing_paper_id, cited_paper_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (paper_id, body.cited_paper_id),
    )
    return {"ok": True}


@router.delete("/papers/{paper_id}/citations/{cited_id}", status_code=204)
def remove_citation(paper_id: UUID, cited_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id, "editor")
    conn.execute(
        "DELETE FROM citations WHERE citing_paper_id = %s AND cited_paper_id = %s", (paper_id, cited_id)
    )


@router.get("/papers/{paper_id}/citation-lineage")
def citation_lineage(
    paper_id: UUID,
    max_depth: int = Query(10, ge=1, le=25),
    user=Depends(current_user),
    conn=Depends(get_conn),
):
    """Everything this paper builds on, directly or indirectly.

    Depth 1 = papers it cites, depth 2 = papers those cite, and so on. The recursion
    only follows papers the user can see, and `path` stops it from looping if two
    papers (oddly) cite each other.
    """
    require_paper(conn, user, paper_id)
    rows = conn.execute(
        """
        WITH RECURSIVE visible AS (
            SELECT paper_id FROM v_paper_role WHERE user_id = %(uid)s
        ),
        lineage (paper_id, via_id, depth, path) AS (
            SELECT c.cited_paper_id, c.citing_paper_id, 1, ARRAY[c.citing_paper_id, c.cited_paper_id]
            FROM citations c
            WHERE c.citing_paper_id = %(pid)s
              AND c.cited_paper_id IN (SELECT paper_id FROM visible)
          UNION ALL
            SELECT c.cited_paper_id, c.citing_paper_id, l.depth + 1, l.path || c.cited_paper_id
            FROM citations c
            JOIN lineage l ON c.citing_paper_id = l.paper_id
            WHERE l.depth < %(max)s
              AND NOT c.cited_paper_id = ANY (l.path)
              AND c.cited_paper_id IN (SELECT paper_id FROM visible)
        )
        -- DISTINCT ON keeps, for each paper, the shortest route to it.
        SELECT DISTINCT ON (l.paper_id)
               l.paper_id AS id, p.title, p.year, l.depth, l.via_id, l.path
        FROM lineage l JOIN papers p ON p.id = l.paper_id
        ORDER BY l.paper_id, l.depth
        """,
        {"pid": paper_id, "uid": user["id"], "max": max_depth},
    ).fetchall()
    rows.sort(key=lambda r: (r["depth"], r["year"] or 0))
    return rows


@router.get("/citations/graph")
def citation_graph(user=Depends(current_user), conn=Depends(get_conn)):
    """Every paper the user can see and every citation between them."""
    nodes = conn.execute(
        """
        SELECT p.id, p.title, p.year,
               (SELECT count(*) FROM citations c WHERE c.cited_paper_id = p.id) AS cited_by_count
        FROM papers p JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %s
        """,
        (user["id"],),
    ).fetchall()
    edges = conn.execute(
        """
        SELECT c.citing_paper_id AS source, c.cited_paper_id AS target
        FROM citations c
        JOIN v_paper_role a ON a.paper_id = c.citing_paper_id AND a.user_id = %(uid)s
        JOIN v_paper_role b ON b.paper_id = c.cited_paper_id  AND b.user_id = %(uid)s
        """,
        {"uid": user["id"]},
    ).fetchall()
    return {"nodes": nodes, "edges": edges}
