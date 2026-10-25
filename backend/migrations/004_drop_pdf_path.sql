-- PDFs now live in paper_files (migration 003), so the on-disk path is no longer used.
ALTER TABLE papers DROP COLUMN pdf_path;
