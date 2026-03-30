-- Migration 005: Ground truth sets
-- Used by: GT management endpoints, FOBE100 seed script

CREATE TABLE gt_sets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_by  UUID REFERENCES auth.users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gt_set_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    set_id      UUID NOT NULL REFERENCES gt_sets(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_by    UUID REFERENCES auth.users(id),
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(set_id, document_id)
);

CREATE INDEX idx_gt_set_documents_set ON gt_set_documents (set_id);
CREATE INDEX idx_gt_set_documents_doc ON gt_set_documents (document_id);
