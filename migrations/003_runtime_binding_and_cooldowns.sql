ALTER TABLE source_health ADD COLUMN runtime_fingerprint TEXT;
ALTER TABLE source_health ADD COLUMN runtime_json TEXT;
ALTER TABLE source_health ADD COLUMN evidence_root TEXT;

ALTER TABLE campaigns ADD COLUMN cooldown_hours INTEGER NOT NULL DEFAULT 24
    CHECK (cooldown_hours > 0);

ALTER TABLE proposed_actions ADD COLUMN cooldown_hours INTEGER;

ALTER TABLE actions ADD COLUMN runtime_fingerprint TEXT;
ALTER TABLE actions ADD COLUMN profile_lock_lease_id TEXT;
ALTER TABLE actions ADD COLUMN evidence_root TEXT;
ALTER TABLE actions ADD COLUMN evidence_sha256 TEXT;
ALTER TABLE actions ADD COLUMN submission_started_at TEXT;

CREATE INDEX idx_actions_proposal_finished
    ON actions(proposed_action_id, status, finished_at);
