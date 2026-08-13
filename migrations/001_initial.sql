PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT NOT NULL,
    account_alias TEXT NOT NULL DEFAULT 'default',
    status TEXT NOT NULL CHECK (status IN (
        'unverified', 'healthy', 'challenged', 'blocked_auth',
        'rate_limited', 'paused', 'waiting_for_reauth', 'error'
    )),
    route TEXT,
    browser_version TEXT,
    checked_at TEXT NOT NULL,
    certified_at TEXT,
    detail TEXT,
    evidence_path TEXT,
    PRIMARY KEY (source, account_alias)
);

CREATE TABLE IF NOT EXISTS source_records (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    price_minor INTEGER,
    currency TEXT,
    posted_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    raw_evidence_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    score REAL,
    score_explanation_json TEXT,
    stage TEXT NOT NULL DEFAULT 'new',
    UNIQUE (source, external_id),
    UNIQUE (source, canonical_url)
);

CREATE INDEX IF NOT EXISTS idx_source_records_dedupe
    ON source_records(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_source_records_stage_score
    ON source_records(stage, score DESC);

CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    business_alias TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposed_actions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    account_alias TEXT NOT NULL DEFAULT 'default',
    campaign_id TEXT REFERENCES campaigns(id),
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'pending_approval', 'approved', 'executing',
        'succeeded', 'rejected', 'expired', 'failed', 'needs_reconciliation'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    proposed_action_id TEXT NOT NULL REFERENCES proposed_actions(id),
    payload_hash TEXT NOT NULL,
    approver TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved', 'rejected', 'expired', 'consumed')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_action
    ON approvals(proposed_action_id, status);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    proposed_action_id TEXT NOT NULL REFERENCES proposed_actions(id),
    approval_id TEXT NOT NULL REFERENCES approvals(id),
    source TEXT NOT NULL,
    action_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'executing', 'succeeded', 'failed', 'needs_reconciliation'
    )),
    platform_external_id TEXT,
    platform_url TEXT,
    evidence_path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_class TEXT,
    error_detail TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_thread_id TEXT NOT NULL,
    external_message_id TEXT NOT NULL,
    related_action_id TEXT REFERENCES actions(id),
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    body_redacted TEXT NOT NULL,
    received_at TEXT NOT NULL,
    intent TEXT,
    is_hot INTEGER NOT NULL DEFAULT 0 CHECK (is_hot IN (0, 1)),
    stage TEXT NOT NULL DEFAULT 'new',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source, external_message_id)
);

CREATE TABLE IF NOT EXISTS source_cursors (
    source TEXT NOT NULL,
    cursor_kind TEXT NOT NULL,
    cursor_value TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source, cursor_kind)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    source TEXT,
    mode TEXT NOT NULL CHECK (mode IN (
        'disabled', 'observe', 'draft', 'approved_write', 'template_reply'
    )),
    status TEXT NOT NULL CHECK (status IN (
        'running', 'succeeded', 'failed', 'blocked', 'cancelled'
    )),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    cursor_before TEXT,
    cursor_after TEXT,
    seen_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_class TEXT,
    error_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_source_started
    ON job_runs(source, started_at DESC);
