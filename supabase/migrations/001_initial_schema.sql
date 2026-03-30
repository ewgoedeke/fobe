-- FOBE Initial Schema
-- Supabase Postgres migration for the public server

-- ══════════════════════════════════════════════════════
-- DOCUMENTS
-- ══════════════════════════════════════════════════════

CREATE TABLE documents (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          TEXT UNIQUE NOT NULL,
  entity_name   TEXT NOT NULL,
  gaap          TEXT NOT NULL CHECK (gaap IN ('IFRS', 'UGB', 'HGB')),
  industry      TEXT DEFAULT 'general',
  jurisdiction  TEXT,
  fiscal_year   INT,
  currency      TEXT DEFAULT 'EUR',
  unit_scale    INT DEFAULT 1,
  language      TEXT DEFAULT 'de',
  page_count    INT,
  pdf_url       TEXT,
  docling_url   TEXT,
  source_path   TEXT,
  docling_status TEXT DEFAULT 'none' CHECK (docling_status IN ('none', 'uploaded', 'ingested')),
  status        TEXT DEFAULT 'ingested' CHECK (status IN ('ingested', 'structured', 'tagged', 'reviewed')),
  ingested_at   TIMESTAMPTZ DEFAULT now(),
  created_by    UUID REFERENCES auth.users(id)
);

-- ══════════════════════════════════════════════════════
-- TOC & DOCUMENT STRUCTURE
-- ══════════════════════════════════════════════════════

CREATE TABLE toc_sections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  label           TEXT NOT NULL,
  statement_type  TEXT NOT NULL,
  start_page      INT NOT NULL,
  end_page        INT,
  note_number     TEXT,
  sort_order      INT DEFAULT 0,
  source          TEXT DEFAULT 'auto' CHECK (source IN ('auto', 'human')),
  validated       BOOLEAN DEFAULT FALSE,
  validated_by    UUID REFERENCES auth.users(id),
  validated_at    TIMESTAMPTZ,
  UNIQUE(document_id, label, start_page)
);

CREATE TABLE internal_edges (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_type     TEXT NOT NULL CHECK (source_type IN ('table_row', 'toc_section')),
  source_id       TEXT NOT NULL,
  target_type     TEXT NOT NULL CHECK (target_type IN ('toc_section', 'table')),
  target_id       TEXT NOT NULL,
  edge_type       TEXT NOT NULL CHECK (edge_type IN ('note_ref', 'toc_to_section', 'cross_statement')),
  note_number     INT,
  confidence      REAL DEFAULT 1.0,
  validated       BOOLEAN DEFAULT FALSE,
  validated_by    UUID REFERENCES auth.users(id)
);

-- ══════════════════════════════════════════════════════
-- TABLES (from Docling → table_graphs.json)
-- ══════════════════════════════════════════════════════

CREATE TABLE tables (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  table_id            TEXT NOT NULL,
  page_no             INT NOT NULL,
  bbox                JSONB,
  statement_component TEXT,
  classification_method TEXT,
  section_path        TEXT,
  detected_currency   TEXT,
  detected_unit       TEXT,
  column_meta         JSONB,
  UNIQUE(document_id, table_id)
);

CREATE TABLE table_rows (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id        UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
  row_idx         INT NOT NULL,
  label           TEXT,
  row_type        TEXT,
  indent_level    INT DEFAULT 0,
  parent_row_idx  INT,
  note_ref        TEXT,
  bbox            JSONB,
  UNIQUE(table_id, row_idx)
);

CREATE TABLE cells (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  row_id          UUID NOT NULL REFERENCES table_rows(id) ON DELETE CASCADE,
  col_idx         INT NOT NULL,
  raw_text        TEXT,
  parsed_value    DOUBLE PRECISION,
  is_negative     BOOLEAN DEFAULT FALSE,
  bbox            JSONB,
  UNIQUE(row_id, col_idx)
);

-- ══════════════════════════════════════════════════════
-- CONCEPT TAGS
-- ══════════════════════════════════════════════════════

CREATE TABLE row_tags (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  row_id          UUID NOT NULL REFERENCES table_rows(id) ON DELETE CASCADE,
  concept_id      TEXT NOT NULL,
  tag_source      TEXT NOT NULL CHECK (tag_source IN ('pretag', 'structural', 'llm', 'mlp', 'human')),
  confidence      REAL,
  validated       BOOLEAN DEFAULT FALSE,
  validated_by    UUID REFERENCES auth.users(id),
  validated_at    TIMESTAMPTZ,
  UNIQUE(row_id, concept_id)
);

-- ══════════════════════════════════════════════════════
-- ONTOLOGY (loaded from YAML at deploy time)
-- ══════════════════════════════════════════════════════

CREATE TABLE concepts (
  id              TEXT PRIMARY KEY,
  label           TEXT NOT NULL,
  context         TEXT NOT NULL,
  balance_type    TEXT,
  period_type     TEXT,
  unit_type       TEXT,
  is_total        BOOLEAN DEFAULT FALSE,
  mappable        BOOLEAN DEFAULT TRUE
);

CREATE TABLE concept_gaap_labels (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id      TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  gaap            TEXT NOT NULL CHECK (gaap IN ('IFRS', 'UGB', 'HGB')),
  label           TEXT NOT NULL,
  language        TEXT DEFAULT 'en',
  UNIQUE(concept_id, gaap, label, language)
);

CREATE TABLE concept_aliases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id      TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  alias           TEXT NOT NULL,
  language        TEXT DEFAULT 'en',
  UNIQUE(concept_id, alias, language)
);

-- ══════════════════════════════════════════════════════
-- USER REVIEW STATE
-- ══════════════════════════════════════════════════════

CREATE TABLE page_reviews (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES auth.users(id),
  document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  element_type    TEXT NOT NULL,
  page_no         INT,
  reviewed_at     TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, document_id, element_type, page_no)
);

CREATE TABLE classification_overrides (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id        UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES auth.users(id),
  statement_component TEXT NOT NULL,
  comment         TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ══════════════════════════════════════════════════════
-- INDEXES
-- ══════════════════════════════════════════════════════

-- Element Browser: "show all pages tagged PNL"
CREATE INDEX idx_toc_sections_type ON toc_sections(statement_type);
CREATE INDEX idx_tables_component ON tables(statement_component);
CREATE INDEX idx_tables_document ON tables(document_id);

-- Concept search: "all rows tagged FS.PNL.REVENUE"
CREATE INDEX idx_row_tags_concept ON row_tags(concept_id);
CREATE INDEX idx_row_tags_row ON row_tags(row_id);

-- User review tracking
CREATE INDEX idx_page_reviews_user_doc ON page_reviews(user_id, document_id, element_type);

-- Cross-reference lookups
CREATE INDEX idx_internal_edges_doc ON internal_edges(document_id, edge_type);
CREATE INDEX idx_internal_edges_note ON internal_edges(document_id, note_number);

-- Row lookups by table
CREATE INDEX idx_table_rows_table ON table_rows(table_id);

-- Cell lookups by row
CREATE INDEX idx_cells_row ON cells(row_id);
