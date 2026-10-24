from fastapi import APIRouter, Depends, Query

from ..auth import current_user
from ..db import get_conn

router = APIRouter(tags=["search"])

# ts_headline wraps matches in these markers; the frontend turns them into <mark> safely
# (never as raw HTML, so text inside a paper can't inject anything into the page).
HEADLINE_OPTS = "StartSel=⟦, StopSel=⟧, MaxFragments=2, MaxWords=30, MinWords=10, FragmentDelimiter=\" … \""


@router.get("/search")
def full_text_search(
    q: str = Query(min_length=1),
    kind: str | None = Query(None, pattern="^(paper|highlight|note)$"),
    user=Depends(current_user),
    conn=Depends(get_conn),
):
    """Keyword search across papers, highlights and your notes in one ranked list.

    websearch_to_tsquery understands Google-style input: "exact phrase", -exclude, or.
    The GIN indexes on each `search` column make the @@ match fast; ts_rank orders results.
    """
    rows = conn.execute(
        """
        WITH query AS (SELECT websearch_to_tsquery('english', %(q)s) AS tsq),
             visible AS (SELECT paper_id FROM v_paper_role WHERE user_id = %(uid)s)
        SELECT * FROM (
            SELECT 'paper' AS kind, p.id, p.id AS paper_id, p.title AS paper_title, NULL::int AS page,
                   NULL::text AS tag,
                   ts_headline('english', coalesce(p.title || '. ' || p.abstract, p.title), query.tsq, %(opts)s) AS snippet,
                   ts_rank(p.search, query.tsq) AS rank
            FROM papers p, query
            WHERE p.search @@ query.tsq AND p.id IN (SELECT paper_id FROM visible)
          UNION ALL
            SELECT 'highlight', h.id, h.paper_id, p.title, h.page, h.tag,
                   ts_headline('english', h.quote, query.tsq, %(opts)s),
                   ts_rank(h.search, query.tsq)
            FROM highlights h JOIN papers p ON p.id = h.paper_id, query
            WHERE h.search @@ query.tsq AND h.paper_id IN (SELECT paper_id FROM visible)
          UNION ALL
            SELECT 'note', n.id, n.paper_id, p.title, NULL, NULL,
                   ts_headline('english', n.content, query.tsq, %(opts)s),
                   ts_rank(n.search, query.tsq)
            FROM notes n JOIN papers p ON p.id = n.paper_id, query
            WHERE n.search @@ query.tsq AND n.user_id = %(uid)s
        ) results
        WHERE %(kind)s::text IS NULL OR kind = %(kind)s::text
        ORDER BY rank DESC
        LIMIT 50
        """,
        {"q": q, "uid": user["id"], "opts": HEADLINE_OPTS, "kind": kind},
    ).fetchall()
    return rows
