-- 001_denormalize_counts.sql
-- Run in Supabase SQL Editor (Dashboard → SQL Editor)
--
-- Adds denormalized table_count and row_count columns to documents table.
-- These are maintained by triggers on INSERT/DELETE to tables and table_rows.
-- Eliminates the need to JOIN 97K+ table rows on every dashboard load.

-- 1. Add columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS table_count integer NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS row_count integer NOT NULL DEFAULT 0;

-- 2. Backfill from current data
UPDATE documents d SET
  table_count = COALESCE((SELECT count(*) FROM tables t WHERE t.document_id = d.id), 0),
  row_count = COALESCE((
    SELECT count(*) FROM table_rows r
    JOIN tables t ON r.table_id = t.id
    WHERE t.document_id = d.id
  ), 0);

-- 3. Trigger: update table_count on tables INSERT/DELETE
CREATE OR REPLACE FUNCTION update_document_table_count()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE documents SET table_count = table_count + 1 WHERE id = NEW.document_id;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE documents SET table_count = GREATEST(table_count - 1, 0) WHERE id = OLD.document_id;
    -- Also subtract all rows that belonged to this table
    UPDATE documents SET row_count = GREATEST(row_count - (
      SELECT count(*) FROM table_rows WHERE table_id = OLD.id
    ), 0) WHERE id = OLD.document_id;
    RETURN OLD;
  END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_table_count ON tables;
CREATE TRIGGER trg_document_table_count
  AFTER INSERT OR DELETE ON tables
  FOR EACH ROW EXECUTE FUNCTION update_document_table_count();

-- 4. Trigger: update row_count on table_rows INSERT/DELETE
CREATE OR REPLACE FUNCTION update_document_row_count()
RETURNS trigger AS $$
DECLARE
  doc_id uuid;
BEGIN
  IF TG_OP = 'INSERT' THEN
    SELECT document_id INTO doc_id FROM tables WHERE id = NEW.table_id;
    IF doc_id IS NOT NULL THEN
      UPDATE documents SET row_count = row_count + 1 WHERE id = doc_id;
    END IF;
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    SELECT document_id INTO doc_id FROM tables WHERE id = OLD.table_id;
    IF doc_id IS NOT NULL THEN
      UPDATE documents SET row_count = GREATEST(row_count - 1, 0) WHERE id = doc_id;
    END IF;
    RETURN OLD;
  END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_row_count ON table_rows;
CREATE TRIGGER trg_document_row_count
  AFTER INSERT OR DELETE ON table_rows
  FOR EACH ROW EXECUTE FUNCTION update_document_row_count();
