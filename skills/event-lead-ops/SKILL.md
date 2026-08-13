---
name: event-lead-ops
description: Use when operating the event lead-ops marketplace system.
version: 0.1.0
author: Justin Bellware
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [events, lead-ops, craigslist, facebook-marketplace, approvals, slack]
    related_skills: []
---

# Event Lead Ops

## Overview

Operate the implemented event-lead-ops scaffold on an always-on Hermes VPS.
Currently implemented operations are configuration validation, database setup,
redacted status/health, approver administration, normalization/scoring library
code, and the approval-gated execution state machine. Live collection, drafting,
Slack routing, response polling, and platform writers remain unimplemented and
must not be scheduled or represented as operational.

The canonical database and repository configuration control state. Slack is the
intended operator interface, but project-specific Slack routing is not connected
yet and Slack will never be the source of truth.

## When to Use

Use this skill for implemented status/configuration/database operations and to
evaluate requests against the future contracts below. For an unimplemented
operation, report the blocker; do not attempt or simulate it.

- Check event lead-ops or browser health
- Collect Craigslist or Facebook Marketplace opportunities
- Score or review local event leads
- Prepare platform-specific ad/listing drafts
- Review, approve, reject, or reconcile an external action
- Poll replies to the operator's own ads/listings
- Pause or resume a source
- Produce a daily operations report

Do not use it to contact scraped sellers automatically, bypass a platform challenge, create accounts, rotate proxies to evade enforcement, or automate payment.

## Load Project Rules

Work from the deployed repository root so `AGENTS.md` is loaded. Read `docs/safety-and-approvals.md` and `docs/operator-runbook.md` before any external action.

Expected checkout:

```text
/home/hermes/event-lead-ops
```

Expected runtime root:

```text
/home/hermes/.local/share/event-lead-ops
```

## Operating Modes

- `disabled`: no source work.
- `observe`: certified read-only health and collection.
- `draft`: observe plus draft generation.
- `approved_write`: only a specific valid approval may execute.
- `template_reply`: unavailable until separately certified.

When mode is unclear, use `observe`. Never infer approval from casual language.

## Standard Procedure

1. **Resolve scope.** Identify source, account alias, requested operation, campaign, and mode. Completion: exactly one bounded job is defined.
2. **Run the browser council.** For new live workflows or route changes, execute the five-round comparison in `docs/browser-execution-council.md`. Completion: primary/fallback route and verification contract are recorded.
3. **Check health.** Read current health, browser route, certification age, and pause state. Completion: source is `healthy` for the exact route or work stops.
4. **Run only implemented deterministic code.** The CLI currently supports
   database setup, redacted status/health, configuration validation, and approver
   administration. Normalization, scoring, approval, and audit primitives are
   callable library APIs. Reject collection, drafting, Slack routing, response
   polling, and platform execution requests as “not implemented” until executable
   commands, tests, and deployment evidence exist.
5. **Preserve evidence.** Save redacted artifacts outside Git. Completion: evidence path/hash is attached to the record or action.
6. **Apply policy.** Reject prohibited actions, duplicates, expired approvals, changed payloads, or unhealthy sources. Completion: the decision is auditable.
7. **Report through the available operator channel.** Include stable IDs, counts,
   health changes, blockers, and pending approvals without secrets. Use Slack only
   after project-specific routing is implemented and verified. Completion: the
   operator can choose the next action.

## Future Read-Only Collection Contract — Not Implemented

### Craigslist

When implemented and certified, public Tampa searches may run without login
after a bounded pilot. Enforce configured pages, delays, search/category
allowlist, and canonical listing IDs. Never reply to discovered ads automatically.

### Facebook Marketplace

When implemented, use only the certified persistent browser profile. Confirm
expected Marketplace and Tampa context without exposing private identity. Stop
on checkpoint, CAPTCHA, warning, account-change prompt, or selector-contract
failure.

## Future Drafting Contract — Not Implemented

A draft must include platform, account alias, campaign, title, description, category, price, location, media list, claims, duplicate/cooldown result, and risk flags. Validate business facts against local untracked configuration.

Editing a draft changes its hash and requires a new approval.

## Future Platform-Execution Contract — Writer Not Implemented

The database state machine below is implemented and tested, but no platform
writer invokes it. A future writer must complete every step before an external
write:

1. Verify source mode is `approved_write` and health is `healthy`.
2. Load one `approved` and unexpired approval for the proposed action.
3. Hash the current canonical payload and compare it to the approval.
4. Check the idempotency key for an existing action.
5. Atomically consume the approval and create the execution row.
6. Execute one platform action.
7. Capture platform ID/URL, timestamp, and confirmation evidence.
8. Mark success, failure, or `needs_reconciliation`.

If submission state is ambiguous, do not retry. Reconcile the platform account first.

## Future Response-Monitoring Contract — Not Implemented

When implemented, poll only threads tied to the operator's own listings/ads. Use
a deterministic cursor and dedupe by external message ID. Classify and draft
replies, but require approval. Escalate pricing, availability, deposits,
contracts, refunds, disputes, emergencies, and unusual requests.

## Pause Conditions

Immediately pause the source on:

- CAPTCHA or login checkpoint
- Account warning
- Rate limit or posting rejection
- Unexpected payment screen
- Material UI/selector-contract change
- Duplicate-action uncertainty
- Possible submit without confirmation

Report once on transition and once after recovery.

## Slack Response Shape

```text
Event Lead Ops — <status/job>
Source: <source> | Mode: <mode> | Health: <health>
Run: <job/action id>
Seen / New / Updated / Duplicate: n / n / n / n
Pending approvals: n
Blockers: <none or exact blocker>
Evidence: <safe reference>
Next safe action: <one action>
```

## Common Pitfalls

1. **Claiming cookie portability.** Only a live VPS read-only certification proves the intended route.
2. **Retrying an uncertain submit.** Reconcile first; retrying may create a duplicate.
3. **Treating Slack as approval storage.** Persist an approval row and payload hash.
4. **Running two gateways or browsers on one identity.** Keep one gateway and one profile owner.
5. **Putting secrets in logs.** Use aliases and redacted health evidence.
6. **Enabling all schedules at once.** Promote one bounded source job after its gate passes.

## Verification Checklist

- [ ] Repo root and local configuration identified
- [ ] Source mode and health checked
- [ ] Exact browser route is currently certified
- [ ] Deterministic job and database audit completed
- [ ] No secret values entered logs or Slack
- [ ] No external action without exact valid approval
- [ ] Idempotency checked before execution
- [ ] Confirmation evidence or reconciliation state recorded
- [ ] Slack report names the exact blocker or verified outcome
