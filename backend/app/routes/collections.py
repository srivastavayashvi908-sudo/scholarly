from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..access import require_collection, require_highlight, require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import CollectionIn, MemberIn

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("")
def list_collections(user=Depends(current_user), conn=Depends(get_conn)):
    """Collections I own plus collections shared with me."""
    return conn.execute(
        """
        SELECT c.id, c.name, c.description, c.created_at, c.owner_id, u.name AS owner_name,
               CASE WHEN c.owner_id = %(uid)s THEN 'owner' ELSE m.role END AS role,
               (SELECT count(*) FROM paper_collections pc WHERE pc.collection_id = c.id)     AS paper_count,
               (SELECT count(*) FROM highlight_collections hc WHERE hc.collection_id = c.id) AS highlight_count,
               (SELECT count(*) FROM collection_members cm WHERE cm.collection_id = c.id)    AS member_count
        FROM collections c
        JOIN users u ON u.id = c.owner_id
        LEFT JOIN collection_members m ON m.collection_id = c.id AND m.user_id = %(uid)s
        WHERE c.owner_id = %(uid)s OR m.user_id IS NOT NULL
        ORDER BY c.created_at DESC
        """,
        {"uid": user["id"]},
    ).fetchall()


@router.post("", status_code=201)
def create_collection(body: CollectionIn, user=Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        "INSERT INTO collections (owner_id, name, description) VALUES (%s, %s, %s) RETURNING *",
        (user["id"], body.name, body.description),
    ).fetchone()


@router.get("/{collection_id}")
def get_collection(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    role = require_collection(conn, user, collection_id)
    row = conn.execute(
        """SELECT c.*, u.name AS owner_name FROM collections c JOIN users u ON u.id = c.owner_id
           WHERE c.id = %s""",
        (collection_id,),
    ).fetchone()
    return {**row, "role": role}


@router.patch("/{collection_id}")
def update_collection(collection_id: UUID, body: CollectionIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "editor")
    return conn.execute(
        "UPDATE collections SET name = %s, description = %s WHERE id = %s RETURNING *",
        (body.name, body.description, collection_id),
    ).fetchone()


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "owner")
    conn.execute("DELETE FROM collections WHERE id = %s", (collection_id,))


# ---------------------------------------------------------------- papers in a collection

@router.get("/{collection_id}/papers")
def collection_papers(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id)
    return conn.execute(
        """
        SELECT p.id, p.title, p.authors, p.year, p.venue, pc.added_at,
               coalesce(s.status, 'to_read') AS status,
               (SELECT count(*) FROM highlights h WHERE h.paper_id = p.id) AS highlight_count
        FROM paper_collections pc
        JOIN papers p ON p.id = pc.paper_id
        LEFT JOIN paper_reading_state s ON s.paper_id = p.id AND s.user_id = %s
        WHERE pc.collection_id = %s
        ORDER BY p.year NULLS LAST, p.title
        """,
        (user["id"], collection_id),
    ).fetchall()


@router.post("/{collection_id}/papers/{paper_id}", status_code=201)
def add_paper(collection_id: UUID, paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "editor")
    require_paper(conn, user, paper_id)
    conn.execute(
        "INSERT INTO paper_collections (paper_id, collection_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (paper_id, collection_id),
    )
    return {"ok": True}


@router.delete("/{collection_id}/papers/{paper_id}", status_code=204)
def remove_paper(collection_id: UUID, paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "editor")
    conn.execute(
        "DELETE FROM paper_collections WHERE paper_id = %s AND collection_id = %s", (paper_id, collection_id)
    )


# ---------------------------------------------------------------- comparison table

@router.get("/{collection_id}/comparison")
def comparison(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Pivot the EAV rows in paper_attributes into one row per paper.

    jsonb_object_agg turns the many (attr_name, attr_value) rows of each paper into a single
    JSON object, e.g. {"dataset": "ImageNet", "metric": "F1=0.89"}; columns = every attr_name used.
    """
    require_collection(conn, user, collection_id)
    rows = conn.execute(
        """
        SELECT p.id, p.title, p.year,
               coalesce(jsonb_object_agg(a.attr_name, a.attr_value)
                        FILTER (WHERE a.attr_name IS NOT NULL), '{}'::jsonb) AS attributes
        FROM paper_collections pc
        JOIN papers p ON p.id = pc.paper_id
        LEFT JOIN paper_attributes a ON a.paper_id = p.id
        WHERE pc.collection_id = %s
        GROUP BY p.id
        ORDER BY p.year NULLS LAST, p.title
        """,
        (collection_id,),
    ).fetchall()
    columns = conn.execute(
        """
        SELECT a.attr_name, count(*) AS papers_with_it
        FROM paper_collections pc JOIN paper_attributes a ON a.paper_id = pc.paper_id
        WHERE pc.collection_id = %s
        GROUP BY a.attr_name
        ORDER BY count(*) DESC, a.attr_name
        """,
        (collection_id,),
    ).fetchall()
    return {"columns": [c["attr_name"] for c in columns], "rows": rows}


# ---------------------------------------------------------------- highlights (virtual document)

@router.get("/{collection_id}/highlights")
def collection_highlights(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id)
    return conn.execute(
        """
        SELECT h.id, h.quote, h.tag, h.color, h.page, h.paper_id, p.title AS paper_title,
               u.name AS user_name, hc.added_at
        FROM highlight_collections hc
        JOIN highlights h ON h.id = hc.highlight_id
        JOIN papers p ON p.id = h.paper_id
        JOIN users u ON u.id = h.user_id
        WHERE hc.collection_id = %s
        ORDER BY h.tag NULLS LAST, p.title, h.page
        """,
        (collection_id,),
    ).fetchall()


@router.post("/{collection_id}/highlights/{highlight_id}", status_code=201)
def add_highlight(collection_id: UUID, highlight_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "editor")
    require_highlight(conn, user, highlight_id)
    conn.execute(
        "INSERT INTO highlight_collections (highlight_id, collection_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (highlight_id, collection_id),
    )
    return {"ok": True}


@router.delete("/{collection_id}/highlights/{highlight_id}", status_code=204)
def remove_highlight(collection_id: UUID, highlight_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "editor")
    conn.execute(
        "DELETE FROM highlight_collections WHERE highlight_id = %s AND collection_id = %s",
        (highlight_id, collection_id),
    )


# ---------------------------------------------------------------- sharing

@router.get("/{collection_id}/members")
def list_members(collection_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id)
    return conn.execute(
        """
        SELECT u.id AS user_id, u.name, u.email, 'owner' AS role, c.created_at AS added_at
        FROM collections c JOIN users u ON u.id = c.owner_id WHERE c.id = %(c)s
        UNION ALL
        SELECT u.id, u.name, u.email, m.role, m.added_at
        FROM collection_members m JOIN users u ON u.id = m.user_id WHERE m.collection_id = %(c)s
        ORDER BY added_at
        """,
        {"c": collection_id},
    ).fetchall()


@router.put("/{collection_id}/members")
def share(collection_id: UUID, body: MemberIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_collection(conn, user, collection_id, "owner")
    target = conn.execute("SELECT id FROM users WHERE email = lower(%s)", (body.email,)).fetchone()
    if target is None:
        raise HTTPException(404, "No user with that email. Ask them to register first.")
    if target["id"] == user["id"]:
        raise HTTPException(400, "You already own this collection")
    conn.execute(
        """
        INSERT INTO collection_members (collection_id, user_id, role) VALUES (%s, %s, %s)
        ON CONFLICT (collection_id, user_id) DO UPDATE SET role = EXCLUDED.role
        """,
        (collection_id, target["id"], body.role),
    )
    return list_members(collection_id, user, conn)


@router.delete("/{collection_id}/members/{member_id}", status_code=204)
def unshare(collection_id: UUID, member_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    # The owner can remove anyone; members can remove themselves (leave).
    if member_id != user["id"]:
        require_collection(conn, user, collection_id, "owner")
    conn.execute(
        "DELETE FROM collection_members WHERE collection_id = %s AND user_id = %s", (collection_id, member_id)
    )
