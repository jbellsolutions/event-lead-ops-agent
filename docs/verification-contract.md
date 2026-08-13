# Verification Contract

No component is “working” without evidence at the relevant layer.

## Static/Core Verification

- Python package builds/imports.
- Built wheel installs into a clean environment and can initialize a database.
- SQL migration applies to a new SQLite database.
- YAML examples parse.
- Unit tests pass.
- Re-importing fixtures is idempotent.
- Approval payload edits invalidate approval.
- Expired/consumed approvals fail closed.
- Unknown Slack member IDs cannot approve.
- Source mode/health/certification are loaded from SQLite, not caller arguments.
- Current runtime fingerprint and exact custodian-owned profile-lock lease match the
  certified reservation through terminal recording.
- Certification older than 24 hours fails closed.
- A second browser process cannot own the same profile.
- Successful writes require platform ID, HTTPS URL, and an owner-only
  action-bound JSON evidence manifest inside the certified evidence root; its
  hash is persisted and rechecked before any retry.
- The executor records a durable submission marker immediately before the first
  platform-side submit. The same transaction consumes a one-use execution
  capability and returns the immutable SQLite-owned payload; caller-held payloads
  are not adapter inputs. Post-marker uncertainty can only reconcile, never retry.
- SQLite rejects proposal/approval identity rewrites, mismatched action snapshots,
  action runtime/profile/evidence reservation rewrites, restored capabilities,
  cleared or replaced submission markers, terminal outcomes with live
  capabilities, and terminal-status rollback to `executing`.
- Stale/ambiguous executions require reconciliation; only evidenced
  `confirmed_no_submit` retries get one new attempt after persisted cooldown.
- `observe` and `draft` modes reject external execution.
- Secret and forbidden-file scan passes.
- Relative Markdown links resolve.

## Craigslist Observe Pilot

- Target: configured Tampa search URLs.
- No account required.
- Assert expected page/search identity.
- Collect a bounded number of pages.
- Normalize required fields.
- Preserve source URL and evidence hash.
- Confirm zero posts, replies, account actions, or payments.
- Report unique count and duplicate count.

## Facebook Observe Pilot

- Use the intended persistent VPS profile.
- Assert the expected account/session without exposing identity in public artifacts.
- Confirm Tampa Marketplace/search identity.
- Collect a bounded search sample.
- Preserve redacted evidence.
- Confirm no listing, message, reaction, account, or payment mutation.
- Stop on checkpoint, CAPTCHA, warning, or uncertain account state.
- Stop before payment/card entry/checkout; human takeover occurs outside automation.

## External-Write Pilot

Run only after observe and draft gates pass.

For one approved test action:

- Validate exact payload and approval hash.
- Acquire execution/idempotency lock.
- Execute once.
- Capture platform URL/ID, screenshot, and timestamp.
- Verify the operator's account shows the new action.
- Ensure a retry does not duplicate it.
- Monitor for immediate platform warning.

## Slack Verification

- Hermes Mac1 responds in the dedicated channel.
- `status` reflects database state.
- Approval message contains exact payload and expiry.
- One approval produces one action.
- Duplicate approval clicks are harmless.
- Source pause blocks queued writes.

## Publication Verification

Before publishing a repository revision:

- Inspect all tracked file names.
- Scan current contents and full Git history for secrets.
- Verify `.gitignore` covers runtime data.
- Run tests and lint.
- Fetch the public repository and verify README, AGENTS, implementation plan, and license exist.
