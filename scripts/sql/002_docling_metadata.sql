-- 002_docling_metadata.sql
-- Add denormalized docling stats to documents table.
-- These are extracted from docling_elements.json at ingest time.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS docling_text_count  INT,
  ADD COLUMN IF NOT EXISTS docling_table_count INT,
  ADD COLUMN IF NOT EXISTS docling_page_count  INT,
  ADD COLUMN IF NOT EXISTS docling_size_kb     INT,
  ADD COLUMN IF NOT EXISTS tg_page_count       INT;
