-- =====================================================================
-- Indexes, views, triggers and functions
-- =====================================================================

-- ---------------------------------------------------------------------
-- Indexes
-- Postgres indexes primary keys automatically, but NOT foreign keys.
-- These make joins/lookups on the FK side fast.
-- ---------------------------------------------------------------------
CREATE INDEX idx_papers_owner            ON papers(owner_id);
CREATE INDEX idx_highlights_paper        ON highlights(paper_id);
CREATE INDEX idx_highlights_user         ON highlights(user_id, created_at);
CREATE INDEX idx_notes_paper             ON notes(paper_id);
CREATE INDEX idx_paper_collections_coll  ON paper_collections(collection_id);
CREATE INDEX idx_highlight_coll_coll     ON highlight_collections(collection_id);
CREATE INDEX idx_collection_members_user ON collection_members(user_id);
CREATE INDEX idx_paper_concepts_concept  ON paper_concepts(concept_id);
CREATE INDEX idx_prereq_prerequisite     ON concept_prerequisites(prerequisite_id);
CREATE INDEX idx_citations_cited         ON citations(cited_paper_id);
CREATE INDEX idx_reading_sessions_user   ON reading_sessions(user_id, started_at);
CREATE INDEX idx_comments_highlight      ON highlight_comments(highlight_id);
CREATE INDEX idx_reference_dois_doi      ON paper_reference_dois(doi);
CREATE INDEX idx_papers_doi              ON papers(lower(doi));   -- expression index

-- GIN indexes make full-text search (@@) fast instead of scanning every row.
CREATE INDEX idx_papers_search     ON papers     USING gin(search);
CREATE INDEX idx_highlights_search ON highlights USING gin(search);
CREATE INDEX idx_notes_search      ON notes      USING gin(search);

-- HNSW indexes make nearest-neighbour vector search fast (approximate).
CREATE INDEX idx_paper_emb     ON paper_embeddings     USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_highlight_emb ON highlight_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_concept_emb   ON concept_embeddings   USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------
-- Access control views
-- A user can see a paper if they own it, or it sits in a collection they
-- own or are a member of.
-- ---------------------------------------------------------------------
CREATE VIEW v_paper_access AS
    SELECT p.id AS paper_id, p.owner_id AS user_id, 'owner'::text AS role
    FROM papers p
UNION
    SELECT pc.paper_id, c.owner_id, 'editor'
    FROM paper_collections pc JOIN collections c ON c.id = pc.collection_id
UNION
    SELECT pc.paper_id, cm.user_id, cm.role
    FROM paper_collections pc JOIN collection_members cm USING (collection_id);

-- Collapse the above to the single strongest role per (user, paper).
CREATE VIEW v_paper_role AS
SELECT user_id, paper_id,
       (array_agg(role ORDER BY CASE role WHEN 'owner'  THEN 3
                                          WHEN 'editor' THEN 2
                                          ELSE 1 END DESC))[1] AS role
FROM v_paper_access
GROUP BY user_id, paper_id;

-- Dashboard helper: highlight counts per user per tag.
CREATE VIEW v_tag_counts AS
SELECT user_id, coalesce(tag, 'untagged') AS tag, count(*) AS n
FROM highlights
GROUP BY user_id, coalesce(tag, 'untagged');

-- ---------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------

-- Keep updated_at fresh on every UPDATE.
CREATE FUNCTION trg_set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER papers_updated_at BEFORE UPDATE ON papers
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
CREATE TRIGGER notes_updated_at BEFORE UPDATE ON notes
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- Stamp finished_at when a paper's status becomes 'done' (and clear it otherwise).
CREATE FUNCTION trg_reading_state() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'done' THEN
        IF TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'done' THEN
            NEW.finished_at := now();
        END IF;
    ELSE
        NEW.finished_at := NULL;
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER reading_state_bi BEFORE INSERT OR UPDATE ON paper_reading_state
    FOR EACH ROW EXECUTE FUNCTION trg_reading_state();

-- ---------------------------------------------------------------------
-- Stored function: the days a user was active (read or highlighted),
-- in their own time zone. Used by the streak + calendar queries.
-- ---------------------------------------------------------------------
CREATE FUNCTION activity_days(p_user uuid, p_tz text)
RETURNS TABLE (day date, seconds int, highlights int) AS $$
    WITH reading AS (
        SELECT (started_at AT TIME ZONE p_tz)::date AS day,
               sum(extract(epoch FROM ended_at - started_at))::int AS seconds
        FROM reading_sessions
        WHERE user_id = p_user
        GROUP BY 1
    ), marks AS (
        SELECT (created_at AT TIME ZONE p_tz)::date AS day, count(*)::int AS highlights
        FROM highlights
        WHERE user_id = p_user
        GROUP BY 1
    )
    SELECT coalesce(r.day, m.day),
           coalesce(r.seconds, 0),
           coalesce(m.highlights, 0)
    FROM reading r FULL OUTER JOIN marks m ON m.day = r.day
    -- a day counts if you read >= 1 minute or made a highlight
    WHERE coalesce(r.seconds, 0) >= 60 OR coalesce(m.highlights, 0) > 0;
$$ LANGUAGE sql STABLE;
