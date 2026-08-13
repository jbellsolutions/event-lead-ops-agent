# Safety and Approval Model

## Action Classes

| Class | Examples | Initial policy |
|---|---|---|
| Read-only | Health, search, collect, normalize, score | Allowed in `observe` after certification |
| Draft | Generate ad, listing, or reply text | Allowed in `draft`; no platform mutation |
| External write | Post ad/listing, send reply, edit listing | Exact Slack approval required |
| Credential-bearing | Login, cookie/profile migration, proxy setup | Operator-approved maintenance window |
| Payment | Card charge, paid category, renewal fee | Per-action approval at the payment boundary |
| Destructive | Delete listing, revoke account, purge evidence | Explicit approval and separate audit |

## Approval Invariants

An approval contains:

- Approval ID
- Proposed action ID
- SHA-256 hash of the canonical action payload
- Source/account alias
- Approver identity
- Creation and expiration time
- Single-use state

Validation fails when:

- The payload changes
- The approval expires
- The approval was already consumed
- The source is paused or unhealthy
- The mode is not `approved_write`
- A duplicate successful action already exists

## Default Denials

The initial MVP denies:

- Seller/prospect outreach discovered through scraping
- Automatic Facebook replies
- Automatic Craigslist replies
- Multiple-account operation
- Account creation
- CAPTCHA or checkpoint bypass
- Proxy rotation intended to evade limits
- Unreviewed pricing or availability claims
- Card use without immediate approval
- Cross-posting identical content without platform-specific validation

## Pause Conditions

Pause a source immediately on:

- CAPTCHA
- Login checkpoint
- Account warning
- Rate-limit response or posting rejection
- Unexpected payment screen
- Selector contract failure
- Material page-layout change
- Duplicate-action uncertainty
- Missing confirmation evidence after a possible submit

An ambiguous submit is not retried automatically. It enters `needs_reconciliation` until the platform state is checked.

## Response Policy

Initial responses are draft-only. The system may classify an inquiry and produce a draft, but a person approves it.

A future template-reply mode can be certified only for narrow acknowledgments that:

- Make no pricing, availability, contract, refund, or service commitments
- Clearly identify the business
- Provide a truthful next step
- Stop after one acknowledgment
- Escalate hot or unusual replies

## Audit Requirements

Every decision records who/what authorized it, the exact payload hash, the platform result, evidence, and errors. Logs contain redacted aliases rather than secret values.
