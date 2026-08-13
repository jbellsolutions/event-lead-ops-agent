# Session Migration and IP Strategy

## What Can Be Migrated

A persistent browser session may include:

- Cookies
- Local storage and IndexedDB
- Service-worker state
- Browser preferences
- Timezone, locale, and viewport settings
- Account device history built after successful use

Cookies alone do not reproduce a trusted device. Platforms may also evaluate IP reputation, geography, browser/TLS fingerprint, account history, behavior, and risk signals.

## Platform Posture

These are rollout assumptions, not guarantees. Confirm each account with a live read-only VPS pilot.

### Facebook Marketplace

Risk: medium/high.

A session can remain valid after an IP change, but a cloud IP or materially new device can trigger a login checkpoint. Prefer a persistent profile over injecting cookies on every run.

Acceptance gate:

- Marketplace home loads under the intended account.
- Approved Tampa location is visible.
- A saved search or listing page loads.
- No checkpoint, CAPTCHA, warning, or account-change prompt appears.
- No messages, listings, or account settings are changed.

If challenged, stop. Resolve login once in the persistent VPS profile, or route that same profile through a stable home/residential exit and recertify.

### Craigslist

Public search collection requires no account session and should be the first production lane.

Account posting risk is separate. The initial repository found no basis to assume a transferable account session. Prefer one deliberate login from the VPS profile, then retain that profile. Payment/card screens require explicit per-action approval and are outside the unattended MVP.

Acceptance gate:

- Public Tampa search pages load and paginate within configured limits.
- For account mode, the account page loads without challenge.
- No ad is posted, renewed, deleted, or paid for during health verification.

### Skool

Not part of the initial event MVP. Treat as medium risk. Authentication tokens may be long-lived, but WAF tokens can depend on browser and network context. Migrate a persistent profile and run a same-origin read-only group test before enabling collection.

### LinkedIn

Not part of the initial event MVP. Treat as high risk. Use read-only mode and conservative account behavior. Do not migrate directly into automatic views, reactions, invitations, or messages.

### ReferralNova

Not part of the initial event MVP. Prefer its documented authenticated API/token flow over browser automation when available. Token refresh and expiry are the main concerns.

## Migration Procedure

1. Create an owner-only runtime directory on the VPS.
2. Create an empty platform profile.
3. Select one migration method:
   - One-time interactive login in the VPS profile (preferred), or
   - Encrypted transfer of a browser storage-state export through SSH.
4. Set `0700` on profile directories and `0600` on secret files.
5. Start one browser process with `scripts/run_persistent_browser.sh` or
   `event-lead-ops-browser`. It holds `.event-lead-ops.lock` in the profile for
   the entire browser lifetime; a second process fails immediately. Never launch
   raw Chromium against these profile directories.
6. Run the platform's read-only acceptance gate.
7. Save a redacted health record and screenshot outside Git.
8. Mark the certification with route, egress class, browser version, and date.
9. Persist `certified_at`; the database derives expiry using the source policy's
   `certification_ttl_hours`, which may not exceed 24. Any route, egress, proxy,
   browser-major-version, profile, account alias, provider, or headed/headless-mode
   change invalidates it immediately.
10. Enable `observe` mode only.
11. Re-run certification after any invalidating environment change.

## Egress Choices

### Direct VPS IP

Cheapest and simplest. Pilot first. It may work for public Craigslist reads and some account sessions, but no platform is guaranteed to accept it.

### Home exit node

A low-power home device (router, small server, or similar) can route the VPS browser through the normal home connection even when the Mac is off. This preserves residential geography without requiring the Mac itself.

### Stable residential/ISP proxy

A dedicated, stable Tampa/Florida route can reduce cloud-IP mismatch. It is not the same as the operator's exact home IP. Use one sticky identity per account and recertify after changes.

### Rotating proxies

Not appropriate for the account MVP. Rotating an authenticated social account across IPs increases identity inconsistency and can look suspicious. Do not use rotation to evade enforcement.

## Secret Handling

- Do not upload cookies through Slack, GitHub, Sheets, dashboards, or issue trackers.
- Do not place cookies in command arguments that may appear in process lists.
- Prefer interactive login or file transfer over encrypted SSH.
- Avoid repeated cookie export/import. A persistent profile should become the authoritative session owner.
- Retain only the evidence needed to operate and troubleshoot.
- Revoke sessions after suspected exposure.
