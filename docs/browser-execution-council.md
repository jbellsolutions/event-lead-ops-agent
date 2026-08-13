# Browser Execution Council

Every live browser workflow starts with a five-round council. This is an execution contract, not optional prose.

## Round 1: Classify

Record:

- Read-only or external write
- Public or authenticated
- Single page, repeatable job, broad crawl, or response monitoring
- Anti-bot/session sensitivity
- Credential, payment, and privacy exposure
- Required evidence

Facebook Marketplace is authenticated and high sensitivity. Craigslist public discovery is a public-read lane; account posting is authenticated and may cross a payment boundary.

## Round 2: Identify Eligible Lanes

Evaluate the lanes actually configured and available on the target deployment:

1. Persistent VPS browser profile with direct VPS egress
2. Persistent VPS browser profile through a stable home exit
3. Persistent VPS browser profile through one stable residential/ISP route
4. Existing Mac bridge while the Mac is online
5. Hosted persistent browser provider certified for the workflow class
6. Public HTTP/crawl provider for Craigslist read discovery

Fast Search is a source-discovery lane only. It does not replace target-site extraction or authenticated browser verification.

## Round 3: Compare at Least Three Viable Options

When three are available, compare:

- Current readiness evidence
- Authentication/profile persistence
- IP/geography continuity
- Anti-bot fit
- Cost per run and recurring cost
- Data completeness
- External-write capability
- Failure evidence and debugging access

Do not call a provider ready based only on configuration or marketing. Require a fresh doctor/health result or verified run for the relevant workflow class.

## Round 4: Readiness, Cost, Evidence, and Safety

Before selection, state:

- Required API key or environment variable if blocked
- Estimated run/crawl cost where known
- Readiness date/evidence
- Whether the lane is certified for read-only or external write
- Approval and account-health implications
- Stop conditions and fallback

## Round 5: Select Execution and Verification

Select one primary lane, one fallback, and an escalation path. Define a verification contract before navigating.

### Recommended initial event MVP

| Workflow | Primary | Fallback | Escalation |
|---|---|---|---|
| Craigslist public discovery | Configured industrial/public-read provider or certified VPS browser | Direct public HTTP/browser read | Stable residential route if measured blocking occurs |
| Craigslist account posting | Persistent VPS profile | Mac recovery bridge | Stable home/residential egress and recertification |
| Facebook Marketplace read | Persistent VPS profile | Mac recovery bridge | Stable home/residential egress and recertification |
| Facebook listing publication | Same profile used in certified read/draft pilot | No automatic fallback | Pause and require new certification |

Do not silently fall back from a certified profile to a different provider for external writes.

## Provider Readiness Record

Store a redacted record outside Git:

```json
{
  "workflow": "facebook_marketplace.observe",
  "provider": "persistent-vps-profile",
  "route": "direct-vps",
  "status": "healthy",
  "certified_for": "read_only",
  "checked_at": "ISO-8601",
  "browser_version": "major.minor",
  "evidence_path": "runtime-only path",
  "blocker": null
}
```

A browser-major-version, egress, proxy, profile, or provider change invalidates external-write certification.
