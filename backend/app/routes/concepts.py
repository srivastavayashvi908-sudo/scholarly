from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from ..access import require_concept
from ..auth import current_user
from ..db import get_conn
from ..models import ConceptIn, KnownIn, PrerequisiteIn
from ..services import embeddings
from ..services.concept_ai import concept_key

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


def lock_prerequisites(conn) -> None:
    """Serialize edge inserts so two simultaneous requests can't each pass the cycle check
    and together create a cycle (A->B and B->A at the same moment). Released at commit."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('concept_prerequisites'))")


def find_cycle(conn, concept_id, prerequisite_id) -> list | None:
    """If adding "concept_id requires prerequisite_id" would close a loop, return the loop.

    A cycle appears exactly when the new prerequisite ALREADY (directly or indirectly)
    requires concept_id, so we walk the prerequisites of the new prerequisite and look
    for concept_id. The walk's path is then the cycle we'd create.
    """
    row = conn.execute(
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
        {"pre": prerequisite_id, "cid": concept_id},
    ).fetchone()
    return row["path"] if row else None


@router.post("/{concept_id}/prerequisites", status_code=201)
def add_prerequisite(concept_id: UUID, body: PrerequisiteIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Add the edge "concept_id requires prerequisite_id", rejecting it if it would create a cycle."""
    concept = require_concept(conn, user, concept_id)
    prereq = require_concept(conn, user, body.prerequisite_id)
    if concept_id == body.prerequisite_id:
        raise HTTPException(409, "A concept can't be its own prerequisite")

    lock_prerequisites(conn)
    cycle = find_cycle(conn, concept_id, body.prerequisite_id)
    if cycle:
        names = conn.execute(
            "SELECT id, name FROM concepts WHERE id = ANY(%s)", (cycle,)
        ).fetchall()
        name_of = {n["id"]: n["name"] for n in names}
        loop = [concept["name"]] + [name_of[i] for i in cycle]
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


@router.put("/{concept_id}/known")
def set_known(concept_id: UUID, body: KnownIn, user=Depends(current_user), conn=Depends(get_conn)):
    """Tick "I already know this": it then counts as learned for Read next and learning paths."""
    require_concept(conn, user, concept_id)
    return conn.execute(
        "UPDATE concepts SET known = %s WHERE id = %s RETURNING *", (body.known, concept_id)
    ).fetchone()


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


# ---------------------------------------------------------------- AI extraction

def merge_ai_concepts(conn, user, paper_id, found: list[dict]) -> dict:
    """Merge the AI's concepts for one paper into the user's graph.

    - Concepts are matched to existing ones by a loose name key, so papers share nodes.
    - Prerequisite edges go through the same cycle check as hand-made ones; an edge that
      would close a loop is skipped instead of failing the whole extraction.
    - The paper's previous AI links are replaced; links you added by hand are kept.
    """
    lock_prerequisites(conn)
    existing = {
        concept_key(r["name"]): r["id"]
        for r in conn.execute("SELECT id, name FROM concepts WHERE owner_id = %s", (user["id"],))
    }
    ids, new_rows = {}, []
    for c in found:
        key = concept_key(c["name"])
        if key in existing:
            ids[key] = existing[key]
            conn.execute(
                """UPDATE concepts SET description = coalesce(description, %s), difficulty = coalesce(difficulty, %s)
                   WHERE id = %s""",
                (c["description"], c["difficulty"], existing[key]),
            )
            continue
        row = conn.execute(
            """
            INSERT INTO concepts (owner_id, name, description, difficulty, source)
            VALUES (%s, %s, %s, %s, 'ai') RETURNING *
            """,
            (user["id"], c["name"], c["description"], c["difficulty"]),
        ).fetchone()
        existing[key] = ids[key] = row["id"]
        new_rows.append(row)

    links_added = cycles_skipped = 0
    for c in found:
        cid = ids[concept_key(c["name"])]
        for p in c["prerequisites"]:
            pid = ids.get(concept_key(p))
            if pid is None or pid == cid:
                continue
            if find_cycle(conn, cid, pid):
                cycles_skipped += 1
                continue
            links_added += conn.execute(
                """INSERT INTO concept_prerequisites (concept_id, prerequisite_id, source)
                   VALUES (%s, %s, 'ai') ON CONFLICT DO NOTHING""",
                (cid, pid),
            ).rowcount

    conn.execute(
        """
        DELETE FROM paper_concepts pc USING concepts c
        WHERE c.id = pc.concept_id AND c.owner_id = %s AND pc.paper_id = %s AND pc.source = 'ai'
        """,
        (user["id"], paper_id),
    )
    for c in found:
        if c["relation"]:
            conn.execute(
                """INSERT INTO paper_concepts (paper_id, concept_id, relation, source)
                   VALUES (%s, %s, %s, 'ai') ON CONFLICT (paper_id, concept_id) DO NOTHING""",
                (paper_id, ids[concept_key(c["name"])], c["relation"]),
            )

    for row in new_rows:
        safe_embed(conn, row)
    return {
        "concepts_found": len(found),
        "new_concepts": len(new_rows),
        "links_added": links_added,
        "cycles_skipped": cycles_skipped,
    }
