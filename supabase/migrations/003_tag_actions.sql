-- Migration 003: Create tag_actions table for tagging audit log
-- Used by: queries.py append_tag_log() / get_tag_log(), server.py POST/GET /api/tag-log

CREATE TABLE IF NOT EXISTS tag_actions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_email  TEXT,
    doc_id      TEXT,
    page_no     INTEGER,
    action      TEXT,
    element_type TEXT,
    old_type    TEXT
);

CREATE INDEX idx_tag_actions_timestamp ON tag_actions (timestamp DESC);
CREATE INDEX idx_tag_actions_doc_id ON tag_actions (doc_id);
