# Data Model

The canonical SQLite migrations are in `migrations/`. The wheel force-includes
them as `event_lead_ops/migrations/`, and `db.py` selects the packaged copy after
installation. Migration history is checked before each atomic migration.

## Main Entities

### `source_records`

Normalized external records. Unique by `(source, external_id)` with a fallback canonical-URL key.

### `campaigns`

Business offers and platform-specific campaign settings.

### `proposed_actions`

Immutable drafts for external actions. The canonical JSON payload is hashed.

### `approvals`

Single-use, expiring authorization tied to the proposed-action hash.

### `authorized_approvers`

Database-owned external identities allowed to approve (for example, an
authenticated Slack member ID mapped to a redacted operator alias).

### `source_policies`

Authoritative source/account mode; callers cannot assert write mode.

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
draft -> pending_approval -> approved -> executing -> [submission_started_at] -> succeeded
                     |              |          |                 |
                     v              v          v                 v
                  rejected       expired   evidenced failed   needs_reconciliation
                                           (pre-submit only)  (post-submit uncertainty)
```

`submission_started_at` is a durable boundary on the action row, not a separate
status value. The writer records it immediately before the first platform-side
submit. Each new action also stores immutable canonical `payload_json` and its
hash. SQLite triggers make proposal identity, approval identity, and action
reservation identity immutable; action insertion must join the exact approved
proposal and approval. SQLite stores only a one-use execution-capability hash;
the raw capability stays with the successful reserver and is consumed by the
same transaction that sets the one-way `submission_started_at` marker. That
transaction decodes and freezes the payload from the action row itself, rather
than from caller-controlled reservation properties. Every terminal or
reconciliation transition also consumes any remaining capability, and SQLite
rejects reopening a terminal action as `executing`. Terminal evidence is an
owner-only JSON manifest
bound to the exact source, account, proposal, action, runtime, outcome, and
result identity; SQLite stores its SHA-256.

### Source health

```text
unknown -> healthy -> challenged / rate_limited / blocked_auth / paused
                        \---------------------------> healthy after recertification
```
