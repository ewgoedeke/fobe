-- Phase C: additions for Element Browser → Supabase migration
--
-- page_offset:  PDF page offset (e.g. eurotelesites_2024 uses 98)
-- page_dims:    per-page {width, height} from table_graphs.json pages dict
-- rank_tags:    MLP page-level predictions from rank_tags.json
-- user_id:      make nullable until auth is wired up

ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_offset INT DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_dims JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS rank_tags JSONB;

ALTER TABLE page_reviews ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE classification_overrides ALTER COLUMN user_id DROP NOT NULL;

-- Backfill known page offsets
UPDATE documents SET page_offset = 98 WHERE slug = 'eurotelesites_2024';
