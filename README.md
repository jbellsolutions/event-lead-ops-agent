# Event Lead Ops Agent

A production-minded blueprint and testable Python core for running a local event-business lead operation through an always-on Hermes Agent in Slack.

The first implementation target is **Tampa Bay events** using:

- Craigslist public listing discovery and approval-gated ad posting
- Facebook Marketplace listing discovery, approval-gated listing publication, and inquiry monitoring
- An existing always-on Hermes VPS as the control plane
- Persistent browser profiles stored outside Git
- Slack as the command, review, approval, and alert surface

> This repository does not contain browser cookies, tokens, customer data, payment details, or private account identifiers.

## Status

This is an **implementation-ready handoff repository**, not a claim that production posting automation is already live. It includes:

- Architecture and deployment decisions
- A platform risk and session-migration plan
- A staged implementation backlog
- A normalized data model and immutable, upgrade-tested SQLite migrations
- Deterministic policy, dedupe, queue, and source-contract code
- Event-business example configuration
- A Hermes skill and project instructions for another agent
- Tests for the core safety and idempotency invariants

Live account login, browser selector capture, and posting verification must be completed against the operator's own accounts without committing secrets.

**Hand this link to another agent with [`HANDOFF.md`](HANDOFF.md) as the entry point.** See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the exact built-vs-pending boundary.

## Recommended Architecture

```text
Slack
  |
  v
Existing Hermes Mac1 gateway on the always-on VPS
  |
  +--> cron / job queue / SQLite / reports / approvals
  |
  +--> persistent VPS browser profiles
  |      +--> Facebook Marketplace
  |      +--> Craigslist account
  |
  +--> optional Mac bridge while the Mac is online
         +--> re-authentication
         +--> visual recovery
         +--> local-only capabilities
```

The VPS is the sole Slack and scheduling owner. The Mac is an optional recovery worker, not a daily dependency.

## Why Cookies Alone Are Not a Guarantee

Cookies can establish a session, but platforms can also evaluate IP reputation, geography, TLS/browser fingerprint, local storage, device history, and account behavior. The rollout therefore uses a read-only authentication pilot before any external write.

| Platform | Initial VPS posture | Expected migration risk |
|---|---|---|
| Facebook Marketplace | Persistent profile, read-only health check first | Medium/high: new device or cloud IP may trigger a checkpoint |
| Craigslist public reads | No login required | Low |
| Craigslist account posting | One-time VPS login preferred | Medium: account, payment, and posting controls |
| Skool | Not in the event MVP; persistent profile pilot later | Medium: WAF state can be browser/IP-sensitive |
| LinkedIn | Not in the event MVP; pause writes | High |
| ReferralNova | Not in the event MVP; API/token lane later | Low/medium |

See [docs/session-migration.md](docs/session-migration.md).

## Event-Business MVP

The starter configuration models a Tampa-area event service business. Replace placeholders in `config/business.example.yaml` with the real offer only in an untracked local file.

### Lead collection

Craigslist:

- Search approved Tampa categories and keywords
- Collect listing URL, ID, title, description, price, location, timestamp, images, and reply method
- Score event intent such as weddings, birthdays, corporate events, festivals, venue needs, rentals, entertainment, staffing, and vendor requests
- Exclude jobs, prohibited categories, spam, and irrelevant resale listings

Facebook Marketplace:

- Use approved Tampa-area saved searches and categories
- Collect visible listing metadata and source evidence
- Never contact sellers automatically
- Route qualified opportunities into a review queue

### Ad/listing operation

1. Generate platform-specific drafts from approved campaign templates.
2. Validate category, duplicate cooldown, prohibited claims, image requirements, price, and location.
3. Send exact drafts to Slack.
4. Require an approval ID before publishing.
5. Durably mark the submit boundary immediately before the first platform write.
6. Capture an action-bound evidence manifest, resulting URL, timestamp, screenshot,
   and platform confirmation.
7. Poll only responses tied to the operator's listings.
8. Draft replies; require approval until a narrow response template is explicitly certified.

## Quick Start for an Implementing Agent

1. Read [`AGENTS.md`](AGENTS.md).
2. Read [`docs/implementation-plan.md`](docs/implementation-plan.md).
3. Read [`docs/safety-and-approvals.md`](docs/safety-and-approvals.md).
4. Copy examples to local, ignored files:

   ```bash
   cp config/business.example.yaml config/business.local.yaml
   cp config/platforms.example.yaml config/platforms.local.yaml
   ```

5. Create a virtual environment and run the tests:

   ```bash
   python3.11 -m venv .venv  # or any verified Python >=3.11
   .venv/bin/python -m pip install -e '.[dev]'
   .venv/bin/python -m pytest
   ```

6. Install or link the bundled Hermes skill using the method supported by the target Hermes version.
7. Deploy the project to the existing Hermes Mac1 VPS under a dedicated work directory.
8. Run the platform pilot in `observe` mode. Do not begin with posting.
9. Promote a platform to `draft`, then `approved_write`, only after its acceptance gate passes.

## Operating Modes

| Mode | Allowed |
|---|---|
| `disabled` | Nothing |
| `observe` | Health checks, read-only collection, normalization, scoring |
| `draft` | Observe plus draft generation; no platform writes |
| `approved_write` | Execute a specific unexpired Slack-approved action exactly once |
| `template_reply` | Only a separately approved narrow reply template; not part of initial MVP |

There is no unrestricted autonomous-write mode in the initial design.

## Slack Interface

Use the existing Hermes bot in a dedicated channel such as `#event-lead-ops`.

Example prompts:

```text
status event lead ops
run craigslist observe
run facebook observe
show event opportunities
prepare this week's craigslist ad drafts
prepare a marketplace listing draft for the approved package
show pending approvals
approve PROPOSED_ACTION_ID
pause facebook
browser health
report today
```

Slack is the operator interface, not the canonical database.

## Repository Map

```text
.
├── AGENTS.md
├── HANDOFF.md
├── IMPLEMENTATION_STATUS.md
├── README.md
├── SECURITY.md
├── config/
│   ├── business.example.yaml
│   ├── platforms.example.yaml
│   ├── scoring.example.yaml
│   └── schedules.example.yaml
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── implementation-plan.md
│   ├── operator-runbook.md
│   ├── safety-and-approvals.md
│   ├── session-migration.md
│   ├── slack-operations.md
│   └── verification-contract.md
├── migrations/
│   ├── 001_initial.sql
│   ├── 002_runtime_policy_and_retries.sql
│   ├── 003_runtime_binding_and_cooldowns.sql
│   └── 004_immutable_action_payload.sql
├── skills/
│   └── event-lead-ops/SKILL.md
├── templates/
│   ├── craigslist-ad.example.md
│   ├── facebook-marketplace-listing.example.md
│   └── inquiry-reply.example.md
├── src/event_lead_ops/
│   ├── db.py
│   ├── models.py
│   ├── policy.py
│   ├── scoring.py
│   ├── sources/base.py
│   ├── sources/craigslist.py
│   └── sources/facebook_marketplace.py
└── tests/
```

## Implementation Boundaries

### Implemented scaffold

- Craigslist/Facebook listing normalization helpers (not live collectors)
- Typed source adapter and response-batch contracts
- Approval, authorization, certification, cooldown, retry, and idempotency controls
- Persistent-profile lock/launcher and systemd template
- Config validation and redacted health/status CLI
- Cross-source normalization and dedupe
- Slack/VPS deployment plan

Live collection, draft rendering, Slack UI routing, platform posting, and inquiry
monitoring remain implementation milestones; see `IMPLEMENTATION_STATUS.md`.

### Not included or enabled by default

- Unattended publishing
- Automatic comments or seller messages
- Bulk multi-account operation
- CAPTCHA solving
- Checkpoint bypassing
- Proxy rotation to evade platform enforcement
- Cookie files in source control
- Payment/card automation
- Automated creation of platform accounts

## Documentation

- [Architecture](docs/architecture.md)
- [Deployment to Hermes Mac1](docs/deployment.md)
- [Browser execution council](docs/browser-execution-council.md)
- [Event-business pilot intake](docs/event-business-intake.md)
- [Implementation plan](docs/implementation-plan.md)
- [Session migration and IP strategy](docs/session-migration.md)
- [Safety and approvals](docs/safety-and-approvals.md)
- [Slack operations](docs/slack-operations.md)
- [Data model](docs/data-model.md)
- [Operator runbook](docs/operator-runbook.md)
- [Verification contract](docs/verification-contract.md)

## License

MIT. Platform names are trademarks of their respective owners. This project is not affiliated with Facebook, Meta, Craigslist, Slack, or Hermes Agent.