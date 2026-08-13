CREATE TABLE source_policies (
    source TEXT NOT NULL,
    account_alias TEXT NOT NULL DEFAULT 'default',
    mode TEXT NOT NULL CHECK (mode IN (
        'disabled', 'observe', 'draft', 'approved_write', 'template_reply'
    )),
    certification_ttl_hours INTEGER NOT NULL DEFAULT 24
        CHECK (certification_ttl_hours > 0),
    execution_timeout_minutes INTEGER NOT NULL DEFAULT 15
        CHECK (execution_timeout_minutes > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source, account_alias)
);

CREATE TABLE authorized_approvers (
    provider TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    operator_alias TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, external_user_id)
);

ALTER TABLE proposed_actions ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1;
ALTER TABLE proposed_actions ADD COLUMN retry_of TEXT REFERENCES proposed_actions(id);

CREATE INDEX idx_proposed_actions_campaign_status
    ON proposed_actions(source, account_alias, campaign_id, action_type, status, created_at);

CREATE UNIQUE INDEX idx_proposed_actions_one_retry
    ON proposed_actions(retry_of) WHERE retry_of IS NOT NULL;
