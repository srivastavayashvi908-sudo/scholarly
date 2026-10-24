from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from ..access import require_concept
from ..auth import current_user
from ..db import get_conn
from ..models import ConceptIn, PrerequisiteIn
from ..services import embeddings

router = APIRouter(prefix="/concepts", tags=["concepts"])


def safe_embed(conn, concept) -> None:
    try:
        with conn.transaction():
            embeddings.store_concept_embedding(conn, concept)
    except Exception as e:  # noqa: BLE001
        print(f"embedding failed for concept {concept['id']}: {e}")


@router.get("")
def list_concepts(user=Depends(current_user), conn=Depends(get_conn)):
    return conn.execute(
        """
        SELECT c.*,
               (SELECT count(*) FROM concept_prerequisites p WHERE p.concept_id = c.id)      AS prerequisite_count,
               (SELECT count(*) FROM concept_prerequisites p WHERE p.prerequisite_id = c.id) AS dependent_count,
               (SELECT count(*) FROM paper_concepts pc WHERE pc.concept_id = c.id)           AS paper_count
        FROM concepts c WHERE c.owner_id = %s ORDER BY c.name
        """,
        (user["id"],),
    ).fetchall()


@router.post("", status_code=201)
def create_concept(body: ConceptIn, user=Depends(current_user), conn=Depends(get_conn)):
    try:
        row = conn.execute(
            "INSERT INTO concepts (owner_id, name, description, difficulty) VALUES (%s, %s, %s, %s) RETURNING *",
            (user["id"], body.name.strip(), body.description, body.difficulty),
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, f"You already have a concept called '{body.name}'")
    safe_embed(conn, row)
    return row


@router.get("/graph")
def concept_graph(user=Depends(current_user), conn=Depends(get_conn)):
    """All concepts and prerequisite edges, for the interactive graph view."""
    nodes = list_concepts(user, conn)
    edges = conn.execute(
        """
        SELECT p.concept_id AS source, p.prerequisite_id AS target
        FROM concept_prerequisites p JOIN concepts c ON c.id = p.concept_id
        WHERE c.owner_id = %s
        """,
        (user["id"],),
    ).fetchall()
    return {"nodes": nodes, "edges": edges}


@router.get("/{concept_id}")
def get_concept(concept_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    concept = require_concept(conn, user, concept_id)
    concept["papers"] = conn.execute(
        """
        SELECT p.id, p.title, p.year, pc.relation
        FROM paper_concepts pc JOIN papers p ON p.id = pc.paper_id
        JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %s
        WHERE pc.concept_id = %s ORDER BY pc.relation, p.year
        """,
        (user["id"], concept_id),
    ).fetchall()
    concept["direct_prerequisites"] = conn.execute(
        """SELECT c.id, c.name FROM concept_prerequisites p JOIN concepts c ON c.id = p.prerequisite_id
           WHERE p.concept_id = %s ORDER BY c.name""",
        (concept_id,),
    ).fetchall()
    return concept


@router.patch("/{concept_id}")
def update_concept(concept_id: UUID, body: ConceptIn, user=Depends(current_user), conn=Depends(get_conn)):
    require_concept(conn, user, concept_id)
    try:
        row = conn.execute(
            "UPDATE concepts SET name = %s, description = %s, difficulty = %s WHERE id = %s RETURNING *",
            (body.name.strip(), body.description, body.difficulty, concept_id),
        ).fetchone()
    except UniqueViolation:
        raise HTTPException(409, f"You already have a concept called '{body.name}'")
    safe_embed(conn, row)
    return row


@router.delete("/{concept_id}", status_code=204)
def delete_concept(concept_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_concept(conn, user, concept_id)
    conn.execute("DELETE FROM concepts WHERE id = %s", (concept_id,))


# ---------------------------------------------------------------- prerequisites

@router.get("/{concept_id}/prerequisites")
def prerequisite_chain(concept_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    """The FULL prerequisite chain, in the order you should learn it.

    The recursive CTE walks prerequisite edges outward from the concept:
      - anchor:    the concept's direct prerequisites (depth 1)
      - recursive: the prerequisites of everything found so far (depth + 1)
    `path` remembers the concepts already on this route so a cycle can never loop forever.

    A concept can be reached by several routes; we keep its LONGEST distance (max depth).
    Sorting by that distance, largest first, gives a valid learning order: if X needs Y,
    every route to X extends to Y, so Y is always at least one step deeper than X.
    """
    concept = require_concept(conn, user, concept_id)
    chain = conn.execute(
        """
        WITH RECURSIVE chain (concept_id, depth, path) AS (
            SELECT p.prerequisite_id, 1, ARRAY[p.concept_id, p.prerequisite_id]
            FROM concept_prerequisites p
            WHERE p.concept_id = %(cid)s
          UNION ALL
            SELECT p.prerequisite_id, ch.depth + 1, ch.path || p.prerequisite_id
            FROM concept_prerequisites p
            JOIN chain ch ON p.concept_id = ch.concept_id
            WHERE NOT p.prerequisite_id = ANY (ch.path)      -- cycle guard
        )
        SELECT c.id, c.name, c.difficulty, max(ch.depth) AS depth
        FROM chain ch JOIN concepts c ON c.id = ch.concept_id
        GROUP BY c.id, c.name, c.difficulty
        ORDER BY depth DESC, c.name
        """,
        {"cid": concept_id},
    ).fetchall()
    ids = [concept_id] + [c["id"] for c in chain]
    edges = conn.execute(
        """SELECT concept_id AS source, prerequisite_id AS target FROM concept_prerequisites
           WHERE concept_id = ANY(%s) AND prerequisite_id = ANY(%s)""",
        (ids, ids),
    ).fetchall()
    return {"concept": {"id": concept["id"], "name": concept["name"]}, "learning_order": chain, "edges": edges}


@router.post("/{concept_id}/prerequisites", status_code=201)
def add_prerequisite(concept_id: UUID, body: PrerequisiteIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Add the edge "concept_id requires prerequisite_id", rejecting it if it would create a cycle.

    A cycle appears exactly when the new prerequisite ALREADY (directly or indirectly)
    requires concept_id. So we walk the prerequisites of the new prerequisite and check
    whether concept_id is among them. If it is, the walk's path is the cycle we'd create.
    """
    concept = require_concept(conn, user, concept_id)
    prereq = require_concept(conn, user, body.prerequisite_id)
    if concept_id == body.prerequisite_id:
        raise HTTPException(409, "A concept can't be its own prerequisite")

    # Serialize edge inserts so two simultaneous requests can't each pass the check
    # and together create a cycle (A->B and B->A at the same moment).
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('concept_prerequisites'))")

    cycle = conn.execute(
        """
        WITH RECURSIVE walk (id, path) AS (
            SELECT %(pre)s::uuid, ARRAY[%(pre)s::uuid]
          UNION ALL
            SELECT p.prerequisite_id, w.path || p.prerequisite_id
            FROM concept_prerequisites p
            JOIN walk w ON p.concept_id = w.id
            WHERE NOT p.prerequisite_id = ANY (w.path)
        )
        SELECT path FROM walk WHERE id = %(cid)s LIMIT 1
        """,
        {"pre": body.prerequisite_id, "cid": concept_id},
    ).fetchone()
    if cycle:
        names = conn.execute(
            "SELECT id, name FROM concepts WHERE id = ANY(%s)", (cycle["path"],)
        ).fetchall()
        name_of = {n["id"]: n["name"] for n in names}
        loop = [concept["name"]] + [name_of[i] for i in cycle["path"]]
        raise HTTPException(
            409,
            f"That would create a cycle: {' → '.join(loop)}. "
            f"'{prereq['name']}' already depends on '{concept['name']}'.",
        )

    conn.execute(
        "INSERT INTO concept_prerequisites (concept_id, prerequisite_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (concept_id, body.prerequisite_id),
    )
    return {"ok": True}


@router.delete("/{concept_id}/prerequisites/{prerequisite_id}", status_code=204)
def remove_prerequisite(concept_id: UUID, prerequisite_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_concept(conn, user, concept_id)
    conn.execute(
        "DELETE FROM concept_prerequisites WHERE concept_id = %s AND prerequisite_id = %s",
        (concept_id, prerequisite_id),
    )


@router.get("/{concept_id}/similar")
def similar_concepts(concept_id: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    require_concept(conn, user, concept_id)
    return conn.execute(
        """
        SELECT c.id, c.name, 1 - (e.embedding <=> me.embedding) AS similarity
        FROM concept_embeddings me
        JOIN concept_embeddings e ON e.concept_id <> me.concept_id
        JOIN concepts c ON c.id = e.concept_id AND c.owner_id = %s
        WHERE me.concept_id = %s
        ORDER BY e.embedding <=> me.embedding
        LIMIT 5
        """,
        (user["id"], concept_id),
    ).fetchall()
