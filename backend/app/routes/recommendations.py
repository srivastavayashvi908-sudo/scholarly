from fastapi import APIRouter, Depends

from ..auth import current_user
from ..db import get_conn

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations")
def what_to_read_next(user=Depends(current_user), conn=Depends(get_conn)):
    """Which unread papers are you ready for?

    1. `learned` (recursive): concepts you ticked as known or that papers you finished
       introduced, PLUS all of their prerequisites (if you understand X, you
       understood what X builds on).
    2. A paper is READY when NOT EXISTS any concept it assumes that you haven't learned.
       (This "no missing requirement" check is relational division.)
    3. Ready papers are ranked by how many new concepts they'd teach you.
       Blocked papers list what's missing and which of your papers would teach it.
    """
    rows = conn.execute(
        """
        WITH RECURSIVE
        visible AS (
            SELECT paper_id FROM v_paper_role WHERE user_id = %(uid)s
        ),
        learned (concept_id) AS (
            SELECT c.id
            FROM concepts c
            WHERE c.owner_id = %(uid)s
              AND (c.known                      -- ticked "I already know this"
                   OR EXISTS (SELECT 1 FROM paper_concepts pc
                              JOIN paper_reading_state s ON s.paper_id = pc.paper_id
                                                        AND s.user_id = %(uid)s AND s.status = 'done'
                              WHERE pc.concept_id = c.id AND pc.relation = 'introduces'))
          UNION
            SELECT cp.prerequisite_id
            FROM concept_prerequisites cp JOIN learned l ON cp.concept_id = l.concept_id
        )
        SELECT p.id, p.title, p.authors, p.year,
               coalesce(s.status, 'to_read') AS status,
               NOT EXISTS (
                   SELECT 1 FROM paper_concepts pc
                   JOIN concepts c ON c.id = pc.concept_id AND c.owner_id = %(uid)s
                   WHERE pc.paper_id = p.id AND pc.relation = 'assumes'
                     AND pc.concept_id NOT IN (SELECT concept_id FROM learned)
               ) AS ready,
               coalesce((SELECT jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name)
                  FROM paper_concepts pc JOIN concepts c ON c.id = pc.concept_id AND c.owner_id = %(uid)s
                 WHERE pc.paper_id = p.id AND pc.relation = 'assumes'
                   AND pc.concept_id NOT IN (SELECT concept_id FROM learned)), '[]') AS missing,
               coalesce((SELECT jsonb_agg(c.name ORDER BY c.name)
                  FROM paper_concepts pc JOIN concepts c ON c.id = pc.concept_id AND c.owner_id = %(uid)s
                 WHERE pc.paper_id = p.id AND pc.relation = 'introduces'
                   AND pc.concept_id NOT IN (SELECT concept_id FROM learned)), '[]') AS teaches,
               (SELECT count(*) FROM paper_concepts pc WHERE pc.paper_id = p.id) AS concept_links
        FROM papers p
        JOIN visible v ON v.paper_id = p.id
        LEFT JOIN paper_reading_state s ON s.paper_id = p.id AND s.user_id = %(uid)s
        WHERE coalesce(s.status, 'to_read') <> 'done'
        """,
        {"uid": user["id"]},
    ).fetchall()

    # Which papers introduce each missing concept? (one query for all of them)
    missing_ids = list({m["id"] for r in rows for m in r["missing"]})
    teachers = {}
    if missing_ids:
        for t in conn.execute(
            """
            SELECT pc.concept_id::text AS concept_id, p.id, p.title
            FROM paper_concepts pc
            JOIN papers p ON p.id = pc.paper_id
            JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %s
            WHERE pc.relation = 'introduces' AND pc.concept_id = ANY(%s::uuid[])
            """,
            (user["id"], missing_ids),
        ).fetchall():
            teachers.setdefault(t["concept_id"], []).append({"id": t["id"], "title": t["title"]})
    for r in rows:
        for m in r["missing"]:
            m["read_first"] = teachers.get(m["id"], [])

    ready = sorted(
        (r for r in rows if r["ready"]),
        key=lambda r: (-len(r["teaches"]), r["status"] != "reading", -(r["concept_links"]), r["title"]),
    )
    blocked = sorted((r for r in rows if not r["ready"]), key=lambda r: (len(r["missing"]), r["title"]))
    return {"ready": ready, "blocked": blocked}
