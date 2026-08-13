# Slack Operations

## Ownership

Use the existing Hermes Mac1 Slack app and VPS gateway. Do not install a second app for this project unless a later security boundary requires it. Use a dedicated channel such as `#event-lead-ops`.

## Conversation Model

- One daily run thread
- One approval card/message per immutable proposed action
- Stable action IDs in every status update
- Direct links to platform evidence only when access is appropriate
- No cookies, tokens, raw profiles, or private exports in Slack

## Operator Prompts

```text
status event lead ops
browser health
run craigslist observe
run facebook observe
show qualified event opportunities
show pending approvals
prepare craigslist ads for this week
prepare the approved Facebook Marketplace listing
approve <approval-id>
reject <approval-id> because <reason>
pause <source>
resume <source>
report today
```

Hermes should translate these into deterministic CLI/library calls. It must not treat conversational “looks good” as an approval unless it resolves to one pending approval and the approval handler records it.

## Status Response Contract

A status response includes:

- Source mode and health
- Last successful read
- Current browser route and certification age
- New/updated record counts
- Pending drafts and approvals
- Last external action and outcome
- Jobs blocked on auth or reconciliation
- Next scheduled bounded jobs

## Approval Message Contract

Each approval request includes:

- Approval ID and expiry
- Platform/account alias
- Action type
- Exact title, description/message, price, location, images, and category
- Campaign and duplicate/cooldown result
- Risk flags
- Source/business context
- Approve/reject/edit instructions

Editing creates a new payload hash and approval request.

## Alerts

Immediate alerts:

- Login checkpoint or CAPTCHA
- Account warning
- Possible duplicate submit
- Hot inquiry
- Failed or expired approval
- Payment boundary reached

Health alerts should fire once on transition and once on recovery, not every poll.
