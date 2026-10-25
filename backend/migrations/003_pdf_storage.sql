-- Store uploaded PDFs inside the database instead of on disk, so the app can run on
-- hosts whose disk is wiped on every restart. One row per paper (1:1 with papers).
CREATE TABLE paper_files (
    paper_id    uuid PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    data        bytea NOT NULL,
    size_bytes  int GENERATED ALWAYS AS (octet_length(data)) STORED,
    uploaded_at timestamptz NOT NULL DEFAULT now()
);
