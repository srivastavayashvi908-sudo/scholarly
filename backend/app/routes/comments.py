from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..access import require_highlight
from ..auth import current_user
from ..db import get_conn
from ..models import CommentIn

router = APIRouter(tags=["comments"])


@router.get("/highlights/{highlight_id}/comments")
def list_comments(highlight_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """Return the whole thread in display order using a recursive CTE.

    `sort_path` is the chain of timestamps from the top-level comment down to this one,
    so ordering by it puts every reply directly under its parent.
    """
    require_highlight(conn, user, highlight_id)
    return conn.execute(
        """
        WITH RECURSIVE thread AS (
            SELECT c.*, 0 AS depth, ARRAY[c.created_at] AS sort_path
            FROM highlight_comments c
            WHERE c.highlight_id = %(hid)s AND c.parent_id IS NULL
          UNION ALL
            SELECT c.*, t.depth + 1, t.sort_path || c.created_at
            FROM highlight_comments c
            JOIN thread t ON c.parent_id = t.id
        )
        SELECT t.id, t.parent_id, t.body, t.created_at, t.depth, t.user_id, u.name AS user_name
        FROM thread t JOIN users u ON u.id = t.user_id
        ORDER BY t.sort_path
        """,
        {"hid": highlight_id},
    ).fetchall()


@router.post("/highlights/{highlight_id}/comments", status_code=201)
def add_comment(highlight_id: UUID, body: CommentIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_highlight(conn, user, highlight_id)
    if body.parent_id:
        parent = conn.execute(
            "SELECT 1 FROM highlight_comments WHERE id = %s AND highlight_id = %s",
            (body.parent_id, highlight_id),
        ).fetchone()
        if not parent:
            raise HTTPException(400, "Reply target is not a comment on this highlight")
    return conn.execute(
        """
        INSERT INTO highlight_comments (highlight_id, user_id, parent_id, body)
        VALUES (%s, %s, %s, %s) RETURNING id, parent_id, body, created_at
        """,
        (highlight_id, user["id"], body.parent_id, body.body),
    ).fetchone()


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(comment_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    # Deleting a comment also deletes its replies (ON DELETE CASCADE on parent_id).
    if conn.execute(
        "DELETE FROM highlight_comments WHERE id = %s AND user_id = %s", (comment_id, user["id"])
    ).rowcount == 0:
        raise HTTPException(404, "Comment not found")
