# Architecture

## Decision

Use the existing Hermes Mac1 deployment as the always-on control plane. Do not create another Slack app or run a second scheduler for the same operation.

## Components

### Hermes Mac1 VPS

Owns:

- Slack gateway and lead-ops conversations
- Bounded schedules
- SQLite source of truth
- Source adapters and scoring
- Approval records and action audit
- Persistent browser processes
- Reports and health alerts

### Persistent browser profiles

Use one profile directory per platform and account. Profile paths are supplied through environment variables and live outside the repository.

```text
$EVENT_LEAD_OPS_RUNTIME/browser-profiles/facebook/
$EVENT_LEAD_OPS_RUNTIME/browser-profiles/craigslist/
```

One worker owns a profile at a time. A file/process lock prevents two Chromium processes from opening the same profile.

### Optional Mac bridge

The Mac bridge is a recovery lane for:

- One-time login or checkpoint resolution
- Comparing behavior against the established residential environment
- Visual debugging
- Local files or desktop-only tools

Daily operation must not require the Mac to stay on.

### Database

SQLite is sufficient for the initial single-worker MVP. It stores normalized records, campaigns, drafts, approvals, actions, responses, source cursors, and job runs. Browser profiles and secret values do not enter the database.

### Slack

Slack is the command and approval surface. It is not the source of truth. Every Slack approval maps to an immutable database row and action-payload hash.

## Request Flow

### Read collection

```text
Hermes cron or Slack request
  -> source job lock
  -> browser/API health check
  -> bounded collection
  -> raw evidence artifact
  -> normalization
  -> idempotent upsert
  -> scoring
  -> Slack/report summary
```

### Approved external action

```text
Draft generator
  -> policy validation
  -> immutable ProposedAction
  -> payload hash
  -> Slack approval request
  -> human approval
  -> approval validation and execution lock
  -> browser action
  -> confirmation evidence
  -> ActionResult and audit record
```

A retry checks the idempotency key before touching the platform.

## Browser Routing

1. Use the persistent VPS profile if its read-only certification is current.
2. If the profile is challenged, pause the source and notify Slack.
3. Use the Mac bridge only for recovery or an explicitly requested comparison.
4. If the VPS cloud IP is the blocker, test a stable home exit or dedicated residential/ISP egress with a fresh read-only certification.
5. Never rotate identities or proxies to evade a platform warning.

## Offline Behavior

When the Mac is off, Hermes Mac1 remains available. Persistent VPS profiles continue only if certified. Sources with unhealthy sessions enter `blocked_auth` or `waiting_for_reauth`; other jobs continue.

## Observability

Every job records:

- Source and account alias
- Start/end time
- Mode
- Cursor and records seen/inserted/updated
- Browser route and egress class (never proxy credentials)
- Health status
- Evidence paths
- Error class
- Approval/action IDs where relevant

Alerts fire on state transitions, not every failed poll.
