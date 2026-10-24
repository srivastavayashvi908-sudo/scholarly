-- =====================================================================
-- Scholarly: core schema
-- Hand-written so every table, constraint and relationship can be explained.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector: embedding columns + similarity operators

-- ---------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL UNIQUE,
    name          text NOT NULL,
    password_hash text NOT NULL,              -- bcrypt hash, never the raw password
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Papers
-- ---------------------------------------------------------------------
CREATE TABLE papers (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      text NOT NULL,
    authors    text,
    year       int CHECK (year BETWEEN 1500 AND 2100),
    venue      text,
    doi        text,
    arxiv_id   text,
    abstract   text,
    summary    text,                           -- filled in by the LLM
    pdf_url    text,                           -- where the PDF lives on the web
    pdf_path   text,                           -- where our uploaded copy lives on disk
    num_pages  int CHECK (num_pages > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Full-text search vector, kept up to date automatically by Postgres.
    -- Weights: title matters most (A), then authors (B), then abstract (C).
    search tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')),    'A') ||
        setweight(to_tsvector('english', coalesce(authors, '')),  'B') ||
        setweight(to_tsvector('english', coalesce(abstract, '')), 'C')
    ) STORED,
    UNIQUE (owner_id, doi)                     -- no duplicate imports of the same DOI
);

-- Per-user reading state. Status lives here (not on papers) because a paper
-- in a shared collection can be "done" for one user and "to_read" for another.
CREATE TABLE paper_reading_state (
    user_id      uuid NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    paper_id     uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    status       text NOT NULL DEFAULT 'to_read'
                 CHECK (status IN ('to_read', 'reading', 'done')),
    current_page int  NOT NULL DEFAULT 1 CHECK (current_page > 0),
    finished_at  timestamptz,                  -- set by trigger when status becomes 'done'
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, paper_id)
);

-- One row per sitting with a paper. Drives time-spent, the dashboard and streaks.
CREATE TABLE reading_sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    paper_id   uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at   timestamptz NOT NULL DEFAULT now(),  -- pushed forward by heartbeats
    start_page int,
    end_page   int,
    CHECK (ended_at >= started_at)
);

-- ---------------------------------------------------------------------
-- Collections + sharing
-- ---------------------------------------------------------------------
CREATE TABLE collections (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Users a collection is shared with, and what they may do.
CREATE TABLE collection_members (
    collection_id uuid NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    user_id       uuid NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    role          text NOT NULL CHECK (role IN ('viewer', 'editor')),
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, user_id)
);

-- Many-to-many: a paper can be in many collections, a collection holds many papers.
CREATE TABLE paper_collections (
    paper_id      uuid NOT NULL REFERENCES papers(id)      ON DELETE CASCADE,
    collection_id uuid NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, collection_id)
);

-- ---------------------------------------------------------------------
-- Highlights, notes, comments
-- ---------------------------------------------------------------------
CREATE TABLE highlights (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id   uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    quote      text NOT NULL CHECK (length(trim(quote)) > 0),
    tag        text CHECK (tag IN ('methodology', 'limitation', 'result', 'dataset',
                                   'definition', 'quote', 'future_work')),
    color      text CHECK (color ~ '^#[0-9a-fA-F]{6}$'),   -- NULL = use the tag's default colour
    page       int CHECK (page > 0),
    -- Where the highlight sits on the PDF page, as rectangles in 0..1 page coordinates,
    -- e.g. {"rects": [{"x":0.1,"y":0.2,"w":0.5,"h":0.02}]}. NULL for hand-typed quotes.
    position   jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    search tsvector GENERATED ALWAYS AS (to_tsvector('english', quote)) STORED
);

-- Many-to-many: regroup highlights from different papers into a "virtual document".
CREATE TABLE highlight_collections (
    highlight_id  uuid NOT NULL REFERENCES highlights(id)  ON DELETE CASCADE,
    collection_id uuid NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (highlight_id, collection_id)
);

CREATE TABLE notes (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id   uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    user_id    uuid NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    content    text NOT NULL CHECK (length(trim(content)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- Threaded discussion on a highlight. parent_id is a self-reference:
-- a reply points at the comment it answers (NULL = top-level comment).
CREATE TABLE highlight_comments (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    highlight_id uuid NOT NULL REFERENCES highlights(id)         ON DELETE CASCADE,
    user_id      uuid NOT NULL REFERENCES users(id)              ON DELETE CASCADE,
    parent_id    uuid          REFERENCES highlight_comments(id) ON DELETE CASCADE,
    body         text NOT NULL CHECK (length(trim(body)) > 0),
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Cross-paper comparison (EAV: Entity-Attribute-Value)
-- ---------------------------------------------------------------------
CREATE TABLE paper_attributes (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id   uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    attr_name  text NOT NULL,                  -- e.g. 'dataset'
    attr_value text NOT NULL,                  -- e.g. 'ImageNet'
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (paper_id, attr_name)               -- one value per attribute per paper
);

-- ---------------------------------------------------------------------
-- Concept / prerequisite graph
-- ---------------------------------------------------------------------
CREATE TABLE concepts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    description text,
    difficulty  text CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);

-- Self-referencing many-to-many: concept_id requires prerequisite_id first.
-- Cycles (A needs B needs A) are rejected by the API with a recursive query.
CREATE TABLE concept_prerequisites (
    concept_id      uuid NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    prerequisite_id uuid NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (concept_id, prerequisite_id),
    CHECK (concept_id <> prerequisite_id)     -- a concept can't require itself
);

CREATE TABLE paper_concepts (
    paper_id   uuid NOT NULL REFERENCES papers(id)   ON DELETE CASCADE,
    concept_id uuid NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    relation   text NOT NULL CHECK (relation IN ('introduces', 'assumes')),
    PRIMARY KEY (paper_id, concept_id)
);

-- ---------------------------------------------------------------------
-- Citation graph
-- ---------------------------------------------------------------------
CREATE TABLE citations (
    citing_paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    cited_paper_id  uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    PRIMARY KEY (citing_paper_id, cited_paper_id),
    CHECK (citing_paper_id <> cited_paper_id)
);

-- Reference DOIs found when importing a paper. Used to link citations automatically
-- when the referenced paper is (or later becomes) part of the library.
CREATE TABLE paper_reference_dois (
    paper_id uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    doi      text NOT NULL,                    -- stored lower-case
    PRIMARY KEY (paper_id, doi)
);

-- ---------------------------------------------------------------------
-- Semantic search (384 dims = BAAI/bge-small-en-v1.5)
-- ---------------------------------------------------------------------
CREATE TABLE paper_embeddings (
    paper_id   uuid PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    embedding  vector(384) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE highlight_embeddings (
    highlight_id uuid PRIMARY KEY REFERENCES highlights(id) ON DELETE CASCADE,
    embedding    vector(384) NOT NULL
);

CREATE TABLE concept_embeddings (
    concept_id uuid PRIMARY KEY REFERENCES concepts(id) ON DELETE CASCADE,
    embedding  vector(384) NOT NULL
);
