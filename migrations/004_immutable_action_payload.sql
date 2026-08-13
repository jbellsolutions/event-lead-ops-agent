ALTER TABLE actions ADD COLUMN payload_json TEXT;
ALTER TABLE actions ADD COLUMN execution_token_hash TEXT;

UPDATE actions
SET payload_json = (
    SELECT proposed_actions.payload_json
    FROM proposed_actions
    WHERE proposed_actions.id = actions.proposed_action_id
);

UPDATE proposed_actions
SET status = 'needs_reconciliation',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'executing';

UPDATE actions
SET status = 'needs_reconciliation',
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP),
    error_class = COALESCE(error_class, 'migration_interrupted_execution'),
    error_detail = COALESCE(
        error_detail,
        'execution predates immutable payload capability; verify platform state'
    )
WHERE status = 'executing';

CREATE TRIGGER proposed_actions_identity_immutable
BEFORE UPDATE OF source, account_alias, campaign_id, action_type, payload_json,
                 payload_hash, idempotency_key, created_at, attempt, retry_of,
                 cooldown_hours
ON proposed_actions
WHEN NEW.source IS NOT OLD.source
    OR NEW.account_alias IS NOT OLD.account_alias
    OR NEW.campaign_id IS NOT OLD.campaign_id
    OR NEW.action_type IS NOT OLD.action_type
    OR NEW.payload_json IS NOT OLD.payload_json
    OR NEW.payload_hash IS NOT OLD.payload_hash
    OR NEW.idempotency_key IS NOT OLD.idempotency_key
    OR NEW.created_at IS NOT OLD.created_at
    OR NEW.attempt IS NOT OLD.attempt
    OR NEW.retry_of IS NOT OLD.retry_of
    OR NEW.cooldown_hours IS NOT OLD.cooldown_hours
BEGIN
    SELECT RAISE(ABORT, 'proposal identity is immutable');
END;

CREATE TRIGGER approvals_identity_immutable
BEFORE UPDATE OF proposed_action_id, payload_hash, approver, created_at, expires_at
ON approvals
WHEN NEW.proposed_action_id IS NOT OLD.proposed_action_id
    OR NEW.payload_hash IS NOT OLD.payload_hash
    OR NEW.approver IS NOT OLD.approver
    OR NEW.created_at IS NOT OLD.created_at
    OR NEW.expires_at IS NOT OLD.expires_at
BEGIN
    SELECT RAISE(ABORT, 'approval identity is immutable');
END;

CREATE TRIGGER actions_payload_required_on_insert
BEFORE INSERT ON actions
WHEN NEW.status != 'executing'
    OR NEW.payload_json IS NULL
    OR json_valid(NEW.payload_json) = 0
    OR NEW.execution_token_hash IS NULL
    OR length(NEW.execution_token_hash) != 64
    OR NEW.execution_token_hash GLOB '*[^0-9a-f]*'
BEGIN
    SELECT RAISE(ABORT, 'action requires valid payload JSON and execution capability');
END;

CREATE TRIGGER actions_authorization_identity_required
BEFORE INSERT ON actions
WHEN NEW.payload_json IS NOT NULL
    AND json_valid(NEW.payload_json) = 1
    AND NEW.execution_token_hash IS NOT NULL
    AND length(NEW.execution_token_hash) = 64
    AND NEW.execution_token_hash NOT GLOB '*[^0-9a-f]*'
    AND NOT EXISTS (
        SELECT 1
        FROM proposed_actions AS proposed
        JOIN approvals AS approval
          ON approval.id = NEW.approval_id
         AND approval.proposed_action_id = proposed.id
        WHERE proposed.id = NEW.proposed_action_id
          AND proposed.status = 'approved'
          AND approval.status = 'approved'
          AND approval.payload_hash = proposed.payload_hash
          AND proposed.source = NEW.source
          AND proposed.action_type = NEW.action_type
          AND proposed.idempotency_key = NEW.idempotency_key
          AND proposed.payload_json = NEW.payload_json
          AND proposed.payload_hash = NEW.payload_hash
    )
BEGIN
    SELECT RAISE(ABORT, 'action authorization must match stored proposal and approval');
END;

CREATE TRIGGER actions_payload_immutable
BEFORE UPDATE OF payload_json, payload_hash ON actions
WHEN NEW.payload_json IS NOT OLD.payload_json
    OR NEW.payload_hash IS NOT OLD.payload_hash
BEGIN
    SELECT RAISE(ABORT, 'action payload snapshot is immutable');
END;

CREATE TRIGGER actions_execution_token_replacement_blocked
BEFORE UPDATE OF execution_token_hash ON actions
WHEN NEW.execution_token_hash IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'actions.execution_token_hash can only be consumed');
END;

CREATE TRIGGER actions_reservation_identity_immutable
BEFORE UPDATE OF proposed_action_id, approval_id, source, action_type,
                 idempotency_key, started_at, runtime_fingerprint,
                 profile_lock_lease_id, evidence_root
ON actions
WHEN NEW.proposed_action_id IS NOT OLD.proposed_action_id
    OR NEW.approval_id IS NOT OLD.approval_id
    OR NEW.source IS NOT OLD.source
    OR NEW.action_type IS NOT OLD.action_type
    OR NEW.idempotency_key IS NOT OLD.idempotency_key
    OR NEW.started_at IS NOT OLD.started_at
    OR NEW.runtime_fingerprint IS NOT OLD.runtime_fingerprint
    OR NEW.profile_lock_lease_id IS NOT OLD.profile_lock_lease_id
    OR NEW.evidence_root IS NOT OLD.evidence_root
BEGIN
    SELECT RAISE(ABORT, 'action reservation identity is immutable');
END;

CREATE TRIGGER actions_submission_marker_monotonic
BEFORE UPDATE OF submission_started_at ON actions
WHEN OLD.submission_started_at IS NOT NULL
    OR NEW.submission_started_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'action submission marker can only be set once');
END;

CREATE TRIGGER actions_terminal_requires_consumed_capability
BEFORE UPDATE OF status ON actions
WHEN NEW.status IN ('succeeded', 'failed', 'needs_reconciliation')
    AND NEW.execution_token_hash IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'terminal action requires consumed execution capability');
END;

CREATE TRIGGER actions_terminal_cannot_reopen_execution
BEFORE UPDATE OF status ON actions
WHEN OLD.status IN ('succeeded', 'failed', 'needs_reconciliation')
    AND NEW.status = 'executing'
BEGIN
    SELECT RAISE(ABORT, 'terminal action cannot reopen execution');
END;
