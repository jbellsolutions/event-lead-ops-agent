# Deployment

This deploys the **tested control-plane scaffold**. It does not make the unfinished Craigslist/Facebook collectors or writers live.

## Preconditions

- Existing Hermes Mac1 VPS and existing Slack app/gateway; do not create another app.
- Python 3.11 or newer.
- `git`, a verified Chromium-compatible Linux display/headless route, and systemd user services if the persistent-browser fallback is selected.
- The five-round council in `browser-execution-council.md` completed for each browser workflow.
- Owner-approved paths; no cookies, tokens, passwords, payment details, or browser profiles in Git.

## 1. Clone and verify

```bash
git clone https://github.com/jbellsolutions/event-lead-ops-agent.git /home/hermes/event-lead-ops
cd /home/hermes/event-lead-ops
PYTHON_BIN=python3.11 ./scripts/deploy_preflight.sh
```

The preflight installs development dependencies, runs lint/tests/scans, initializes a synthetic database, and prints redacted status.

## 2. Install runtime and browser extra

```bash
cd /home/hermes/event-lead-ops
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[browser]'
.venv/bin/python -m playwright install chromium
```

## 3. Create owner-only runtime paths

```bash
install -d -m 0700 \
  /home/hermes/.config/event-lead-ops \
  /home/hermes/.local/share/event-lead-ops/state \
  /home/hermes/.local/share/event-lead-ops/browser-profiles/facebook \
  /home/hermes/.local/share/event-lead-ops/browser-profiles/craigslist \
  /home/hermes/.local/share/event-lead-ops/artifacts \
  /home/hermes/.local/share/event-lead-ops/logs
install -m 0600 .env.example /home/hermes/.config/event-lead-ops/runtime.env
```

Edit `runtime.env` locally. It may contain paths, `DISPLAY`, and `EVENT_LEAD_OPS_HEADLESS`; secret values belong in the host secret manager. The application enforces `0700` parent directories and `0600` SQLite files.

## 4. Create and validate local configuration

```bash
cp config/business.example.yaml config/business.local.yaml
cp config/platforms.example.yaml config/platforms.local.yaml
cp config/scoring.example.yaml config/scoring.local.yaml
cp config/schedules.example.yaml config/schedules.local.yaml

.venv/bin/event-lead-ops validate-config business config/business.local.yaml
.venv/bin/event-lead-ops validate-config platforms config/platforms.local.yaml
.venv/bin/event-lead-ops validate-config scoring config/scoring.local.yaml
.venv/bin/event-lead-ops validate-config schedules config/schedules.local.yaml
```

Validation fails closed on missing required sections, invalid source modes, unknown source names, insecure/non-HTTPS URLs, missing Tampa location identity, invalid cooldowns, and invalid schedule entries. Canonical sources are `craigslist` and `facebook_marketplace`; `facebook` is the only accepted alias for the latter.

## 5. Initialize and inspect SQLite

```bash
export EVENT_LEAD_OPS_DB=/home/hermes/.local/share/event-lead-ops/state/event-lead-ops.sqlite3
.venv/bin/event-lead-ops --db "$EVENT_LEAD_OPS_DB" init-db
.venv/bin/event-lead-ops --db "$EVENT_LEAD_OPS_DB" status
```

`status` and `health` deliberately redact health detail and evidence paths.

## 6. Register approvers locally

Use the authenticated Slack member ID supplied by the existing Hermes Mac1 event, not a display name and not message text:

```bash
.venv/bin/event-lead-ops --db "$EVENT_LEAD_OPS_DB" approver add \
  --provider slack \
  --external-user-id 'U_REPLACE_WITH_REAL_MEMBER_ID' \
  --operator-alias owner
```

Keep the actual member ID out of Git. The database owns this allowlist. A Slack caller cannot pass an allowlist to the approval function.

## 7. Install the bundled Hermes skill

Install into the active Hermes profile only:

```bash
install -d -m 0700 /home/hermes/.hermes/skills/event-lead-ops
install -m 0600 skills/event-lead-ops/SKILL.md \
  /home/hermes/.hermes/skills/event-lead-ops/SKILL.md
```

Restart or reload the existing Hermes Mac1 gateway using its established service procedure. Do not create a second gateway, bot, or scheduler owner.

## 8. Persistent browser fallback

Super Browser is the orchestration front door. Use this local persistent-Chromium lane only when the five-round council records it as the best viable route for the workflow.

The launcher owns the profile lock for the entire browser lifetime. It is an
observe/reauth/recovery tool, not an external-write executor:

```bash
EVENT_LEAD_OPS_ROOT=/home/hermes/event-lead-ops \
FACEBOOK_PROFILE_DIR=/home/hermes/.local/share/event-lead-ops/browser-profiles/facebook \
./scripts/run_persistent_browser.sh facebook_marketplace
```

For a user service:

```bash
install -d -m 0700 ~/.config/systemd/user
install -m 0600 deploy/systemd/event-lead-ops-browser@.service \
  ~/.config/systemd/user/event-lead-ops-browser@.service
systemctl --user daemon-reload
systemctl --user start event-lead-ops-browser@facebook_marketplace.service
systemctl --user status event-lead-ops-browser@facebook_marketplace.service
```

The service has `Restart=no`: checkpoints, warnings, crashes, and ambiguous state must pause for review rather than loop. A headed route needs a host-provided `DISPLAY`/desktop service. Setting `EVENT_LEAD_OPS_HEADLESS=true` creates a different route and invalidates prior certification.

## 9. Read-only certification

From the intended route/profile, record a live read-only health result with redacted evidence. `approved_write` requires:

- database source policy set to `approved_write` by trusted local code,
- database health `healthy`,
- certification age no more than **24 hours**,
- exact source and account alias match,
- exact unexpired approval,
- no browser/profile/egress/provider/environment change.

Any route, proxy, browser-major-version, headless/display mode, account alias, profile, or provider change invalidates certification.

## 10. Slack approval binding

The existing Hermes Mac1 Slack handler must verify the Slack signature/replay
window, read the event's authenticated member ID, reload the exact proposal,
and call `create_approval()` directly inside the trusted adapter process.

Do not add or wrap a general-purpose approval shell command that accepts a
member ID. Trusted adapter code creates an approval only; it does **not**
execute a browser action. The live executor remains unfinished and must acquire
the certified profile lock itself, call the database reservation API, keep the
same lease through platform interaction, and record terminal evidence before
releasing it.

## 11. Install only the implemented schedule

`config/schedules.example.yaml` is an operator inventory, not automatic Hermes input. Today, only the redacted health command exists. In a Hermes chat with the scheduler tool, create this exact job payload:

```json
{
  "action": "create",
  "name": "event-lead-ops-health",
  "schedule": "0 7 * * *",
  "deliver": "origin",
  "skills": ["event-lead-ops"],
  "enabled_toolsets": ["terminal"],
  "workdir": "/home/hermes/event-lead-ops",
  "prompt": "Run .venv/bin/event-lead-ops --db /home/hermes/.local/share/event-lead-ops/state/event-lead-ops.sqlite3 health. Return the exact redacted JSON summary and alert only on a health-state transition. Do not navigate, collect, post, reply, approve, execute, pay, or schedule another job."
}
```

List jobs and record the returned job ID. Do **not** schedule `collect`, `score`, `report`, or `responses poll`: those CLI commands are not implemented yet. Do not pin a model/provider unless the operator explicitly requires it; the health job needs no browser credentials or environment injection.

## 12. Deployment acceptance

Deployment is not complete until all applicable checks pass:

- clean preflight and wheel install,
- local configs validate,
- private path modes verified,
- existing Hermes Mac1 responds through the existing Slack app,
- authenticated owner approval works and non-owner approval fails,
- one browser process owns each profile and a second process is rejected,
- current live read-only certification exists for the exact route,
- scheduled health job runs from the VPS with the Mac off,
- unfinished collection/write commands are not scheduled or represented as live.
