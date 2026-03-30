-- 007: Pipeline training runs — track configuration, progress, and results

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    created_by UUID REFERENCES auth.users(id),
    config JSONB NOT NULL,              -- {documents, stages, thresholds, use_llm, reclassify, use_ground_truth, gaap_filter}
    progress JSONB DEFAULT '{}',        -- {current_stage, current_doc, docs_completed, docs_total, stage_results}
    summary JSONB,                      -- final summary.json content
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs (status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created ON pipeline_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_run_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,                -- completed | halted_at_gate | error
    halted_at TEXT,                      -- stage name if halted
    stage_results JSONB,                -- per-stage gate metrics
    metrics JSONB,                      -- {tables, data_rows, pretagged_rows, tag_rate, indexed_facts, fact_scores}
    error TEXT,
    UNIQUE(run_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_results_run ON pipeline_run_results (run_id);
