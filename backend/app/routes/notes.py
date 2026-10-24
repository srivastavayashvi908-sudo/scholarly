from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..access import require_paper
from ..auth import current_user
from ..db import get_conn
from ..models import NoteIn

router = APIRouter(tags=["notes"])

# Notes are private: you only ever see your own, even on a shared paper.


@router.get("/papers/{paper_id}/notes")
def list_notes(paper_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    return conn.execute(
        """
        SELECT id, paper_id, content, created_at, updated_at FROM notes
        WHERE paper_id = %s AND user_id = %s ORDER BY created_at DESC
        """,
        (paper_id, user["id"]),
    ).fetchall()


@router.post("/papers/{paper_id}/notes", status_code=201)
def create_note(paper_id: UUID, body: NoteIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_paper(conn, user, paper_id)
    return conn.execute(
        """
        INSERT INTO notes (paper_id, user_id, content) VALUES (%s, %s, %s)
        RETURNING id, paper_id, content, created_at, updated_at
        """,
        (paper_id, user["id"], body.content),
    ).fetchone()


@router.patch("/notes/{note_id}")
def update_note(note_id: UUID, body: NoteIn, user=Depends(current_user), conn=Depends(get_conn)):
    row = conn.execute(
        """
        UPDATE notes SET content = %s WHERE id = %s AND user_id = %s
        RETURNING id, paper_id, content, created_at, updated_at
        """,
        (body.content, note_id, user["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Note not found")
    return row


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    if conn.execute("DELETE FROM notes WHERE id = %s AND user_id = %s", (note_id, user["id"])).rowcount == 0:
        raise HTTPException(404, "Note not found")
