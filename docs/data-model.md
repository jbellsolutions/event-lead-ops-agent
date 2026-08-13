# Data Model

The canonical SQLite schema is in `migrations/001_initial.sql`. The wheel build
includes that directory as `event_lead_ops/migrations/`, and `db.py` selects
the packaged copy after installation.

## Main Entities

### `source_records`

Normalized external records. Unique by `(source, external_id)` with a fallback canonical-URL key.

### `campaigns`

Business offers and platform-specific campaign settings.

### `proposed_actions`

Immutable drafts for external actions. The canonical JSON payload is hashed.

### `approvals`

Single-use, expiring authorization tied to the proposed-action hash.

### `actions`

Execution attempts and outcomes. Successful idempotency keys are unique.

### `responses`

Inbound messages/replies associated with the operator's own listings or ads.

### `job_runs`

Bounded execution records with mode, cursor, counts, health, and errors.

### `source_cursors`

Incremental collection/poll cursors.

## Dedupe

Use the strongest available key in this order:

1. Platform external ID
2. Canonical listing URL
3. Normalized title + location + author/seller alias + posted time bucket
4. Image/content fingerprint for repost detection

Fuzzy matches remain review candidates and are not auto-merged.

## Evidence

Store artifact paths and hashes, not sensitive artifact bodies, in database rows. Evidence directories are outside Git and have retention limits.

## State Machines

### Proposed action

```text
draft -> pending_approval -> approved -> executing -> succeeded
                     |              |          |
                     v              v          v
                  rejected       expired     failed/needs_reconciliation
```

### Source health

```text
unknown -> healthy -> challenged / rate_limited / blocked_auth / paused
                        \---------------------------> healthy after recertification
```
