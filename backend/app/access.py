"""Permission checks shared by the route files.

Roles, weakest to strongest: viewer < editor < owner.
"""
from fastapi import HTTPException

RANK = {"viewer": 1, "editor": 2, "owner": 3}


def paper_role(conn, user_id, paper_id) -> str | None:
    row = conn.execute(
        "SELECT role FROM v_paper_role WHERE user_id = %s AND paper_id = %s",
        (user_id, paper_id),
    ).fetchone()
    return row["role"] if row else None


def require_paper(conn, user, paper_id, min_role: str = "viewer") -> str:
    role = paper_role(conn, user["id"], paper_id)
    if role is None:
        raise HTTPException(404, "Paper not found")
    if RANK[role] < RANK[min_role]:
        raise HTTPException(403, f"You need {min_role} access to this paper")
    return role


def collection_role(conn, user_id, collection_id) -> str | None:
    row = conn.execute(
        """
        SELECT CASE WHEN c.owner_id = %(u)s THEN 'owner' ELSE m.role END AS role
        FROM collections c
        LEFT JOIN collection_members m ON m.collection_id = c.id AND m.user_id = %(u)s
        WHERE c.id = %(c)s
        """,
        {"u": user_id, "c": collection_id},
    ).fetchone()
    return row["role"] if row else None


def require_collection(conn, user, collection_id, min_role: str = "viewer") -> str:
    role = collection_role(conn, user["id"], collection_id)
    if role is None:
        raise HTTPException(404, "Collection not found")
    if RANK[role] < RANK[min_role]:
        raise HTTPException(403, f"You need {min_role} access to this collection")
    return role


def require_concept(conn, user, concept_id) -> dict:
    row = conn.execute(
        "SELECT * FROM concepts WHERE id = %s AND owner_id = %s", (concept_id, user["id"])
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Concept not found")
    return row


def require_highlight(conn, user, highlight_id, own: bool = False) -> dict:
    """Any user who can see the paper can see its highlights; only the author can change one."""
    h = conn.execute("SELECT * FROM highlights WHERE id = %s", (highlight_id,)).fetchone()
    if h is None or paper_role(conn, user["id"], h["paper_id"]) is None:
        raise HTTPException(404, "Highlight not found")
    if own and h["user_id"] != user["id"]:
        raise HTTPException(403, "You can only change your own highlights")
    return h
