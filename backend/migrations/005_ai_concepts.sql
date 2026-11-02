-- Concepts, prerequisite edges and paper links can now be created by the AI extractor.
-- `source` records who made each row, so the UI can mark AI suggestions and a re-run
-- can replace the AI's paper links without touching the ones you added by hand.
ALTER TABLE concepts
    ADD COLUMN source text NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'ai')),
    ADD COLUMN known  boolean NOT NULL DEFAULT false;   -- "I already know this"

ALTER TABLE concept_prerequisites
    ADD COLUMN source text NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'ai'));

ALTER TABLE paper_concepts
    ADD COLUMN source text NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'ai'));
