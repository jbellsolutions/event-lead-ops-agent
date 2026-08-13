# Implementation Plan

## Goal

Deliver an approval-gated Tampa event-business MVP on the existing Hermes Mac1 VPS using Craigslist and Facebook Marketplace.

## Non-Goals for the MVP

- Multi-account operation
- Proxy rotation or anti-detect scaling
- LinkedIn, Skool, or ReferralNova writes
- Unattended replies
- Payment/card automation
- Bypassing platform enforcement

## Milestone 1: Core State and Policies

1. Apply all unapplied SQL migrations in `migrations/` through `init_db()`.
2. Implement config loading and schema validation.
3. Implement source-record upsert and canonical dedupe.
4. Implement proposed-action hashing.
5. Implement expiring single-use approvals.
6. Implement action idempotency and audit.
7. Pass unit tests.

**Gate:** deterministic core tests pass; no browser work required.

## Milestone 2: Craigslist Observe Lane

1. Run the five-round browser council and record provider readiness.
2. Implement bounded public search collection from approved Tampa URLs.
3. Capture fixtures and field contracts.
4. Normalize listing ID, URL, title, description, price, location, posted time, images, and reply path.
5. Add repost/duplicate detection.
6. Score event-business intent.
7. Produce a Slack/report summary.

**Gate:** live read-only pilot; zero account mutations.

## Milestone 3: Facebook Persistent Profile and Observe Lane

1. Run the five-round browser council and record provider readiness.
2. Create the owner-only VPS browser profile directory.
3. Complete a normal one-time login or approved encrypted session transfer.
4. Run the read-only acceptance gate.
5. Implement bounded saved-search/category collection.
6. Stop safely on checkpoints and UI-contract failures.
7. Normalize and score collected listings.

**Re-plan trigger:** if direct VPS egress is challenged, test a stable home/residential exit. Recertify before proceeding.

**Gate:** live read-only pilot with no account changes.

## Milestone 4: Event Campaign and Drafts

1. Complete `event-business-intake.md` and record validated facts.
2. Replace example business configuration in an ignored local file.
3. Define one approved event offer and truthful claims.
4. Add platform-specific templates and image validation.
5. Generate Craigslist and Marketplace drafts.
6. Validate prohibited claims, price, category, location, duplicate cooldown, and media.
7. Send exact drafts to Slack.

**Gate:** operator approves draft quality; nothing has been posted.

## Milestone 5: Slack Approval Path

1. Use the existing Hermes Mac1 bot/channel.
2. Render immutable proposed actions with expiry.
3. Record the approver and payload hash.
4. Reject edits, expiry, duplicates, unhealthy sources, and paused modes.
5. Verify duplicate approvals cannot duplicate execution.

**Gate:** synthetic approval tests pass.

## Milestone 6: One Approved Craigslist Test Ad

1. Establish the Craigslist account profile with normal login.
2. Navigate the posting flow without submitting.
3. Confirm category/payment requirements without entering card data or confirming a charge.
4. If payment is required, stop automation for human takeover; if the draft cannot
   be preserved safely, mark the test blocked.
5. For a no-payment path only, obtain exact approval and submit once.
6. Capture confirmation evidence and verify account state.
7. Test idempotent retry behavior without resubmission.

**Gate:** one verified outcome and no warning/duplicate.

## Milestone 7: One Approved Facebook Marketplace Test Listing

1. Navigate create-listing flow without publishing.
2. Confirm visible category, title, price, photos, description, and Tampa location.
3. Obtain exact approval.
4. Publish once.
5. Capture listing URL/ID and screenshot.
6. Verify the operator account shows it.
7. Monitor for account warning.

**Gate:** one verified outcome and no warning/duplicate.

## Milestone 8: Inquiry Monitoring

1. Collect only threads/replies tied to operator-created ads/listings.
2. Maintain a response cursor.
3. Classify intent and hot-lead signals.
4. Generate draft replies.
5. Require approval for every reply.
6. Poll through a lightweight change detector before invoking an agent.

**Gate:** test inquiry is detected once and reply draft retains context.

## Milestone 9: Bounded Schedules

Enable jobs one by one **only after the named CLI command exists and passes its
live observe gate**. The repository currently ships only `platform-health`:

- `platform-health`
- `collect-craigslist`
- `collect-facebook`
- `score-and-report`
- `poll-responses`
- `daily-brief`

Use the repository as the cron `workdir` so `AGENTS.md` is loaded. Keep each job resumable and under Hermes runtime limits.

**Gate:** shadow-mode day completes with no duplicates or unexplained failures.

## Milestone 10: Expansion Decision

After stable operation, review:

- Account challenge rate
- Session lifetime
- Collection coverage
- Draft approval rate
- Response rate and lead quality
- Duplicate/reconciliation incidents
- Need for home/residential egress

Only then consider Skool, ReferralNova, LinkedIn, additional geographies, or multiple accounts.
