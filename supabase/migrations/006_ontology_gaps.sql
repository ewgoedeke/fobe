-- 006: Ontology gap tracking and concept proposal workflow
--
-- ontology_gaps: rows/labels that don't map to any existing concept
-- concept_proposals: proposed new concepts to fill gaps

CREATE TABLE IF NOT EXISTS ontology_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reported_by UUID REFERENCES auth.users(id),
    document_id TEXT,
    table_id TEXT,
    row_id TEXT,
    row_label TEXT NOT NULL,
    context TEXT,                -- e.g. DISC.PPE, FS.CFS
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'proposed', 'accepted', 'rejected', 'duplicate')),
    resolved_by UUID REFERENCES auth.users(id),
    resolved_at TIMESTAMPTZ,
    proposed_concept_id TEXT,    -- links to concept_proposals.concept_id if proposed
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ontology_gaps_status ON ontology_gaps (status);
CREATE INDEX IF NOT EXISTS idx_ontology_gaps_context ON ontology_gaps (context);
CREATE INDEX IF NOT EXISTS idx_ontology_gaps_document ON ontology_gaps (document_id);

CREATE TABLE IF NOT EXISTS concept_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gap_id UUID REFERENCES ontology_gaps(id),
    proposed_by UUID REFERENCES auth.users(id),
    concept_id TEXT NOT NULL,       -- e.g. DISC.PPE.REVALUATION_SURPLUS
    label TEXT NOT NULL,
    context TEXT,                    -- e.g. DISC.PPE
    balance_type TEXT,              -- debit / credit / null
    period_type TEXT,               -- instant / duration
    unit_type TEXT,                 -- monetary / shares / pure / string
    is_total BOOLEAN DEFAULT false,
    gaap TEXT,                      -- IFRS / UGB / HGB / null (universal)
    aliases TEXT[],                 -- alternative labels (EN + DE)
    rationale TEXT,
    example_docs TEXT[],            -- doc slugs where this concept appears
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'review', 'accepted', 'rejected')),
    reviewed_by UUID REFERENCES auth.users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_concept_proposals_status ON concept_proposals (status);
CREATE INDEX IF NOT EXISTS idx_concept_proposals_gap ON concept_proposals (gap_id);
CREATE INDEX IF NOT EXISTS idx_concept_proposals_context ON concept_proposals (context);
