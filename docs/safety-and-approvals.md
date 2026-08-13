# Safety and Approvals

## Absolute pilot boundaries

During the initial pilot:

- No post, listing, reply, message, comment, account mutation, or external write without one exact unexpired approval.
- **No automated payment, card entry, billing agreement, purchase, checkout confirmation, or paid-category submission.**
- A payment screen pauses the source and requires human takeover outside the automation. If the platform cannot preserve an approved draft without automated payment, that test is blocked—not partially automated.
- CAPTCHA, checkpoint, warning, rate limit, unexpected UI, or uncertain outcome fails closed.

## Immutable approval model

1. Store a canonical proposed action in SQLite.
2. Hash canonical JSON for the payload.
3. Show the exact stored payload and hash in Slack.
4. Authenticate the Slack event user.
5. Require that `(provider, external_user_id)` is active in SQLite's approver allowlist.
6. Create a single-use approval tied to the exact proposed-action ID and payload hash.
7. Expire approval after no more than 30 minutes.
8. Reload proposal/approval from SQLite at execution; never trust caller-constructed metadata.
9. Consume approval atomically with the execution reservation.

A changed payload is a new proposal and requires new approval.

## Authoritative write gates

An external action may begin only when SQLite shows all of the following for the same canonical source and account alias:

- source policy is `approved_write`,
- source health is `healthy`,
- certification is no older than **24 hours**,
- approval is active, unexpired, unused, and bound to the proposal,
- idempotency key has no active/successful execution,
- campaign cooldown permits the action,
- the executing process owns the exact certified profile lock lease,
- the current canonical runtime fingerprint matches certification,
- explicit egress and proxy identities match certification,
- no payment boundary is present.

Callers cannot assert mode, health, allowlisted approvers, or certification freshness.

## Idempotency and retries

The key includes canonical source, account alias, campaign identity, action type, attempt, and canonical payload.

- Identical proposal creation returns the persisted proposal.
- Two simultaneous reservations resolve to one executor and one harmless no-op.
- A stale `executing` action is marked `needs_reconciliation` after the configured timeout.
- `needs_reconciliation` is never automatically retried.
- `failed` is accepted only before the durable submission marker and only as an
  evidenced `confirmed_no_submit`. The executor must call
  `mark_action_submitting()` immediately before the first platform-side submit;
  after that point, any uncertain result is `needs_reconciliation`.
- A confirmed no-submit may be retried only after the database-owned campaign
  cooldown by creating one linked `retry_of` attempt and obtaining a new approval.
- A `succeeded` action cannot be retried.

## Campaign cooldown

Listing publication/repost proposals require a persisted campaign ID. The
database-owned campaign row supplies the positive cooldown; callers cannot
lower it. The database blocks retry proposals and fresh payload variants during
the cooldown window. Exact proposal readback remains idempotent.

## Evidence-required success

A successful external action must record:

- platform external ID,
- HTTPS platform URL,
- owner-only regular JSON evidence manifest inside the certified runtime
  evidence root and outside Git, bound to source/account/proposal/action/runtime,
  outcome, platform ID, and platform URL,
- timestamp and terminal state.

SQLite stores the evidence SHA-256. Retry creation rechecks it and fails if the
manifest changed after terminal recording. Symlinks and group/world-readable
artifacts are rejected.

If submission may have occurred but confirmation is missing, record `needs_reconciliation`, not `succeeded` or `failed`.

## Browser route safety

- Run the five-round Super Browser council before each new workflow or route change.
- Use strict HTTPS allowlists and listing-path validation.
- Do not navigate normalized records with arbitrary schemes/hosts/paths.
- One process owns each persistent profile through the shipped profile lock.
- A write reservation snapshots a unique lock lease and runtime fingerprint;
  terminal recording requires the same still-held lease and fingerprint.
- Route, egress, profile, account alias, provider, browser-major-version, or display/headless changes invalidate certification.
- Do not rotate identities/proxies to evade enforcement.

## Audit and privacy

Store IDs, hashes, states, timestamps, redacted summaries, and runtime evidence paths. Do not put cookies, tokens, account/member identities, raw private messages, payment data, proxy credentials, or browser profiles in Git, Slack reports, or public artifacts.
