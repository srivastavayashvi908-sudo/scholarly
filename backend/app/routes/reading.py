"""Reading sessions: the paper page starts one when opened and sends a heartbeat every
~30 seconds while the tab is visible. A closed tab simply stops the heartbeats, so the
session's ended_at is always the last moment we know you were reading."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..access import require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import SessionIn

router = APIRouter(tags=["reading"])


@router.post("/papers/{paper_id}/sessions", status_code=201)
def start_session(paper_id: UUID, body: SessionIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    # Opening a paper you haven't started moves it to 'reading'.
    conn.execute(
        """
        INSERT INTO paper_reading_state (user_id, paper_id, status) VALUES (%s, %s, 'reading')
        ON CONFLICT (user_id, paper_id) DO UPDATE SET status = 'reading'
        WHERE paper_reading_state.status = 'to_read'
        """,
        (user["id"], paper_id),
    )
    return conn.execute(
        """
        INSERT INTO reading_sessions (user_id, paper_id, start_page, end_page)
        VALUES (%s, %s, %s, %s) RETURNING id, started_at
        """,
        (user["id"], paper_id, body.page, body.page),
    ).fetchone()


@router.post("/sessions/{session_id}/heartbeat")
def heartbeat(session_id: UUID, body: SessionIn, user=Depends(current_user), conn=Depends(get_conn)):
    row = conn.execute(
        """
        UPDATE reading_sessions
           SET ended_at = now(), end_page = coalesce(%s, end_page)
         WHERE id = %s AND user_id = %s
        RETURNING paper_id, extract(epoch FROM ended_at - started_at)::int AS seconds
        """,
        (body.page, session_id, user["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Session not found")
    if body.page:
        conn.execute(
            "UPDATE paper_reading_state SET current_page = %s WHERE user_id = %s AND paper_id = %s",
            (body.page, user["id"], row["paper_id"]),
        )
    return {"seconds": row["seconds"]}
