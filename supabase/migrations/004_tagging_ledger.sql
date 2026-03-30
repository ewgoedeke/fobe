-- Migration 004: Tagging ledger — votes, consensus, and weighted resolution
-- Used by: POST /api/votes/cast, GET /api/votes/{dim}/{target}, GET /api/votes/conflicts/{doc}

-- ══════════════════════════════════════════════════════
-- TAG VOTES
-- ══════════════════════════════════════════════════════

CREATE TABLE tag_votes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dimension   TEXT NOT NULL CHECK (dimension IN ('row_concept', 'table_classification', 'toc_section', 'edge_validation')),
    target_id   UUID NOT NULL,
    user_id     UUID REFERENCES auth.users(id),
    action      TEXT NOT NULL CHECK (action IN ('tag', 'untag', 'dissent')),
    value       TEXT,
    prev_value  TEXT,
    confidence  REAL,
    source      TEXT NOT NULL CHECK (source IN ('pretag', 'structural', 'llm', 'mlp', 'human')),
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tag_votes_target ON tag_votes (dimension, target_id);
CREATE INDEX idx_tag_votes_user ON tag_votes (user_id, created_at DESC);

-- ══════════════════════════════════════════════════════
-- TAG CONSENSUS
-- ══════════════════════════════════════════════════════

CREATE TABLE tag_consensus (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dimension       TEXT NOT NULL,
    target_id       UUID NOT NULL,
    resolved_value  TEXT,
    vote_count      INT NOT NULL DEFAULT 0,
    agree_count     INT NOT NULL DEFAULT 0,
    dissent_count   INT NOT NULL DEFAULT 0,
    total_voters    INT NOT NULL DEFAULT 0,
    confidence      REAL,
    resolved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(dimension, target_id)
);

-- ══════════════════════════════════════════════════════
-- CONSENSUS FUNCTION
-- ══════════════════════════════════════════════════════
-- Weights: human=3, mlp=2, pretag/structural/llm=1
-- Winner: highest weighted sum; ties broken by vote count then most recent.

CREATE OR REPLACE FUNCTION compute_consensus(p_dimension TEXT, p_target_id UUID)
RETURNS VOID AS $$
DECLARE
    v_winner        TEXT;
    v_vote_count    INT;
    v_agree         INT;
    v_dissent       INT;
    v_voters        INT;
    v_confidence    REAL;
BEGIN
    -- Find the winning value by weighted score
    SELECT value INTO v_winner
    FROM (
        SELECT
            value,
            SUM(CASE source
                WHEN 'human' THEN 3
                WHEN 'mlp'   THEN 2
                ELSE 1
            END) AS weighted_score,
            COUNT(*) AS cnt,
            MAX(created_at) AS latest
        FROM tag_votes
        WHERE dimension = p_dimension
          AND target_id = p_target_id
          AND action IN ('tag', 'dissent')
          AND value IS NOT NULL
        GROUP BY value
        ORDER BY weighted_score DESC, cnt DESC, latest DESC
        LIMIT 1
    ) sub;

    -- Compute aggregates
    SELECT
        COUNT(*),
        COUNT(DISTINCT user_id),
        COUNT(*) FILTER (WHERE value = v_winner),
        COUNT(*) FILTER (WHERE action = 'dissent')
    INTO v_vote_count, v_voters, v_agree, v_dissent
    FROM tag_votes
    WHERE dimension = p_dimension
      AND target_id = p_target_id
      AND action IN ('tag', 'dissent');

    -- Confidence: agree ratio weighted
    IF v_vote_count > 0 THEN
        v_confidence := v_agree::REAL / v_vote_count::REAL;
    ELSE
        v_confidence := 0;
    END IF;

    -- Upsert consensus
    INSERT INTO tag_consensus (dimension, target_id, resolved_value, vote_count, agree_count, dissent_count, total_voters, confidence, resolved_at)
    VALUES (p_dimension, p_target_id, v_winner, v_vote_count, v_agree, v_dissent, v_voters, v_confidence, now())
    ON CONFLICT (dimension, target_id)
    DO UPDATE SET
        resolved_value = EXCLUDED.resolved_value,
        vote_count     = EXCLUDED.vote_count,
        agree_count    = EXCLUDED.agree_count,
        dissent_count  = EXCLUDED.dissent_count,
        total_voters   = EXCLUDED.total_voters,
        confidence     = EXCLUDED.confidence,
        resolved_at    = EXCLUDED.resolved_at;
END;
$$ LANGUAGE plpgsql;

-- ══════════════════════════════════════════════════════
-- TRIGGER: auto-recompute consensus on new vote
-- ══════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION trigger_compute_consensus()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM compute_consensus(NEW.dimension, NEW.target_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tag_votes_consensus
    AFTER INSERT ON tag_votes
    FOR EACH ROW
    EXECUTE FUNCTION trigger_compute_consensus();

-- ══════════════════════════════════════════════════════
-- EXTEND row_tags with provenance columns
-- ══════════════════════════════════════════════════════

ALTER TABLE row_tags ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES auth.users(id);
ALTER TABLE row_tags ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
