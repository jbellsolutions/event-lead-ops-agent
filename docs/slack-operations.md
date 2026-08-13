# Slack Operations

Reuse the existing Hermes Mac1 Slack app and gateway. Slack is an authenticated control surface; SQLite is the source of truth.

## Identity and authorization

- The handler reads the authenticated Slack event `user` member ID.
- Display names, message text, channel membership, and button payload claims do not grant approval rights.
- A trusted local administrator registers allowed member IDs with `event-lead-ops approver add`.
- `create_approval()` checks the database-owned `(provider, external_user_id)` allowlist.
- Removing/deactivating an approver is a local database administration task; do not expose it as a general Slack command.
- Approval TTL must be positive and cannot exceed 30 minutes.

## Required trusted adapter binding

There is deliberately no `event-lead-ops approve` shell command. A shell caller
could otherwise impersonate an arbitrary Slack member ID. The Hermes Mac1
Slack adapter must:

1. verify the Slack request signature and replay window at the gateway;
2. read the provider-issued `user` ID from authenticated event context;
3. reload the proposal by ID from SQLite;
4. call `create_approval()` inside the trusted adapter process with that member ID;
5. return only the resulting approval ID and redacted proposal summary.

`create_approval()` reloads the immutable proposal, checks the database-owned
approver allowlist inside the same write transaction, and binds one approval to
the stored proposal ID and payload hash. Approval never executes the platform
action.

Reject:

- approval IDs or hashes supplied as a substitute for a proposed-action ID,
- display-name identities,
- forwarded/copy-pasted command attribution,
- unknown or inactive member IDs,
- edited payloads,
- expired or consumed approvals.

## Exact approval message

Show before approval:

- proposed-action ID,
- canonical source and account alias,
- action type,
- campaign ID when present,
- complete human-readable payload,
- media filenames/hashes,
- location, category, and price,
- payload hash,
- expiry,
- payment boundary (`blocked` during this pilot).

Buttons or command equivalents:

- Approve this exact payload
- Reject
- Request edit
- Pause source

Editing creates a new proposed action and invalidates any prior approval.

## Operator vocabulary

`facebook` resolves only to canonical `facebook_marketplace`; `craigslist` is already canonical. Do not accept fuzzy source names.

These prompts are **routing goals**, not claims that every command exists:

```text
status event lead ops               # bind to implemented status/health CLI
approve PROPOSED_ACTION_ID           # trusted Slack adapter only; no shell CLI
run craigslist observe              # planned collector; reject until implemented/certified
run facebook observe                # planned collector; reject until implemented/certified
pause facebook                      # planned policy administration
show pending approvals              # planned queue view
report today                        # planned reporting command
```

A handler must return “not implemented” for planned operations rather than fabricate output or improvise shell commands.

## Status response

The implemented `event-lead-ops status` command currently returns only redacted:

- source-record count,
- pending-approval count,
- succeeded-action count,
- reconciliation count,
- basic health rows: source, account alias, status, route, checked time, and
  certification time.

It deliberately omits detail text and filesystem paths. The future authenticated
Hermes Mac1 Slack status adapter must add the following database-derived fields
before this richer contract may be described as implemented:

- database schema versions,
- source policy mode and computed certification age/expiry,
- counts by every proposal/approval/action state,
- stale executing counts,
- current profile-lock owner state,
- last bounded job result.

Do not include health detail text, evidence paths, profile paths, private URLs, user/member IDs, tokens, cookies, or message bodies.

## Approval/execution separation

1. Draft code stores immutable proposal.
2. Slack displays exact stored payload.
3. Authenticated allowlisted member approves the proposal ID.
4. Executor separately reloads proposal and approval from SQLite.
5. Executor checks authoritative source policy, exact runtime fingerprint,
   certification freshness, idempotency, and campaign cooldown.
6. Executor acquires the certified profile itself and reserves once while
   holding a unique lock lease. SQLite snapshots the exact canonical payload on
   the action row and returns one opaque execution capability only to the
   successful reserver; duplicate callers receive no capability.
7. Immediately before the first platform-side submit, the executor passes the
   original reservation to `mark_action_submitting()`. That transaction
   revalidates and consumes the capability, durably records the submission
   boundary, and returns the recursively immutable database-owned payload.
   The adapter must submit only from that returned payload, never from the
   caller's proposal or `current_payload` dictionaries.
8. The same process and lock lease span browser interaction and terminal
   action-bound JSON evidence recording inside the certified evidence root.
9. Success requires matching platform ID/HTTPS URL; a pre-submit evidenced
   `confirmed_no_submit` may become retryable only after persisted cooldown.
10. Any uncertain outcome after the submission marker enters
    `needs_reconciliation`; no automatic retry.

Duplicate approval clicks and execution requests must be harmless.

## Alerts

Alert on state transitions:

- healthy -> challenged/blocked/rate-limited,
- certification expired,
- stale execution -> needs reconciliation,
- profile lock contention,
- payment screen,
- platform warning or material UI mismatch.

Never alert with raw private page text or evidence paths.
