# Agent Implementation Contract

This repository is designed to be handed to another coding or operations agent.

## Mission

Implement and deploy a staged event-business lead operation using the existing always-on Hermes Mac1 VPS and Slack connection. The initial platforms are Facebook Marketplace and Craigslist in the Tampa Bay area.

## Read First

1. `README.md`
2. `IMPLEMENTATION_STATUS.md`
3. `docs/architecture.md`
4. `docs/session-migration.md`
5. `docs/browser-execution-council.md`
6. `docs/event-business-intake.md`
7. `docs/safety-and-approvals.md`
8. `docs/implementation-plan.md`
9. `docs/verification-contract.md`

## Non-Negotiable Rules

- Never commit cookies, tokens, browser profiles, customer data, payment details, private account identifiers, or raw message archives.
- Never print secret values in logs, tests, Slack, CI, screenshots, or reports.
- Do not claim a platform session works until a live read-only test passes from the intended VPS browser profile.
- Do not claim that changing IPs is harmless. Record the actual result for each platform/account.
- No post, listing, message, comment, connection request, purchase, card charge, or account change without an explicit, unexpired approval record during the MVP.
- No automated payment, card entry, checkout confirmation, or paid-category submission; stop for human takeover or mark the pilot blocked.
- One approval authorizes one immutable action payload. Editing a draft invalidates the approval.
- Every external action needs an idempotency key, evidence, timestamp, and outcome.
- Stop the source immediately on login checkpoints, account warnings, CAPTCHA, rate limits, unexpected payment screens, or material UI changes.
- Do not bypass platform enforcement, create fake accounts, or use proxy rotation to evade restrictions.
- Run and record the five-round browser council before every new live browser workflow or route change.
- Treat Slack as the control surface and the database as the source of truth.
- Cron triggers bounded jobs; it does not contain the whole business workflow.

## Target Topology

- Existing Hermes Mac1 on the VPS: sole Slack gateway and scheduler owner.
- `/home/hermes/event-lead-ops`: project work directory.
- Persistent browser profiles under a secret, untracked runtime directory.
- VPS SQLite for the MVP.
- Optional Mac bridge for recovery and one-time reauthentication.

## Implementation Order

Follow `docs/implementation-plan.md` in order. Do not skip the read-only pilot and jump directly to posting.

## Required Modes

- `disabled`
- `observe`
- `draft`
- `approved_write`
- `template_reply` only after a separate certification step

Default every source to `disabled` or `observe`.

## CLI boundary

Implemented now:

```text
event-lead-ops init-db
event-lead-ops health [source]
event-lead-ops status
event-lead-ops validate-config <kind> <path>
event-lead-ops approver add ...
event-lead-ops-browser <source> --profile <path>
```

There is deliberately no general-purpose approval CLI. The authenticated Hermes
Mac1 Slack adapter must call the internal `create_approval()` API with the
provider-issued member ID read from trusted event context; message text or a
caller-supplied shell flag cannot establish identity.

Planned, not implemented or schedulable yet:

```text
event-lead-ops collect <source>
event-lead-ops score
event-lead-ops draft <campaign>
event-lead-ops approvals list
event-lead-ops execute <approval-id>
event-lead-ops responses poll <source>
event-lead-ops report
```

Implement planned commands as callable Python functions and tests before exposing
or scheduling them; never invent fake command output.

## Source Adapter Contract

Each source implements:

```python
health() -> HealthReport
collect(cursor: str | None) -> CollectionBatch
normalize(raw: object) -> SourceRecord
prepare_action(record_id: str, campaign_id: str) -> ProposedAction
execute_approved_action(payload: Mapping[str, object]) -> ActionResult
poll_responses(cursor: str | None) -> ResponseBatch
```

Approval validation, execution reservation, runtime/profile-lock attestation, and
the durable submission marker belong to the executor. It must pass the adapter
only the recursively immutable SQLite-derived payload returned by
`mark_action_submitting()`; never pass `ApprovedAction`, `ProposedAction`, or a
caller-owned payload dictionary to an external-write method.

## Testing Expectations

At minimum, verify:

- Database migration applies cleanly.
- Re-importing fixtures creates no duplicate records.
- Approval payload hashes invalidate after edits.
- Expired approvals fail closed.
- Duplicate execution attempts do not repeat the platform action.
- Observe/draft modes cannot execute writes.
- Secret-pattern and forbidden-file scan passes.
- Read-only platform pilot records evidence without changing account state.
- Posting pilot uses a deliberately approved test campaign and captures confirmation evidence.

## Completion Definition

Do not mark the MVP complete until:

1. Both source health checks have live evidence.
2. Craigslist read collection is verified.
3. Facebook read collection is verified or has a documented checkpoint blocker.
4. The database, dedupe, scoring, draft, approval, and audit paths pass tests.
5. One explicitly approved test listing/ad per platform has a verified outcome—or the platform is clearly blocked with evidence.
6. Slack can show status, drafts, approvals, and results through Hermes Mac1.
7. No secrets or private data exist in Git history.
