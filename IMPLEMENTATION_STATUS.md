# Implementation Status

This document prevents handoff ambiguity. Update it as executable milestones land.

## Implemented and Tested

- Python 3.11 package and CLI entry point
- SQLite migration and packaged-wheel migration lookup
- Normalized source-record model
- Craigslist listing normalization helpers
- Facebook Marketplace listing normalization helpers
- Source-record idempotent upsert
- Explainable weighted scoring core
- Canonical action-payload hashing
- Proposed-action and approval persistence
- Single-use, expiring approval checks
- Database-owned approver authorization and immutable-proposal approval API
- Database-backed source policy plus exact runtime-fingerprint certification gate,
  including separate provider, egress, proxy, browser-major-version, display,
  viewport, account, and profile identities
- Campaign-aware idempotency, database-owned cooldown, evidenced no-submit retry,
  stale reconciliation, and terminal audit
- Same-profile-lock-lease execution, an immutable database-owned action-payload
  snapshot, a one-use pre-submit execution capability, a durable pre-submit
  marker, and owner-only action-bound JSON evidence manifests with persisted SHA-256
- SQLite-enforced immutable proposal, approval, action-payload, runtime, profile,
  and evidence identity with exact authorization joins and one-way submit state
- Fail-closed handling for edited payloads and unhealthy sources
- Strict Craigslist/Facebook URL normalization and source aliasing
- Validated business/platform/scoring/schedule configuration
- Owner-only SQLite/runtime permissions and redacted status output
- Persistent browser launcher, cross-process profile lock, and systemd template
- Current-tree/full-history secret scanner with decodable-text coverage
- Hermes skill and existing-gateway deployment instructions
- Repository secret/forbidden-file and relative-link scanner
- CI, lint, unit tests, CLI smoke test, and isolated wheel-install test

## Designed but Not Yet Live-Implemented

- Super Browser provider invocation and provider-readiness persistence
- Craigslist page fetch/pagination/browser extraction
- Facebook persistent-browser lifecycle and selectors
- Source health navigations and screenshot capture
- Campaign template rendering and media validation
- Slack Block Kit or equivalent approval UI
- Hermes command-to-CLI routing
- Actual Craigslist account login/posting flow
- Actual Facebook listing creation flow
- Craigslist relay/account response collector
- Facebook listing-thread response collector
- Runtime job locking, source cursors, and dead-letter worker
- Google Sheets or here.now publishing
- Installed Hermes cron jobs

## Live Verification Not Yet Claimed

The public repository alone does not prove:

- Facebook accepts the account/profile from the VPS route
- Craigslist account posting works from the VPS
- The exact Facebook or Craigslist category/fee fields for the operator's offer
- A Marketplace or Craigslist listing has been published
- A response has been detected or drafted
- Slack commands have operated this project on the target VPS
- Mac-off browser behavior has been tested

The implementing agent must update this file only with real evidence and must keep credential-bearing artifacts outside Git.
