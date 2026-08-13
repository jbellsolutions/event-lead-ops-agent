# Deployment to Hermes Mac1

This project is designed to be installed into an existing Hermes gateway. Do not create a new Slack app.

## Prerequisites

On the VPS:

- Hermes Agent is installed and `hermes doctor` is healthy.
- The existing Slack gateway is running.
- The operator account can write `/home/hermes`.
- Python 3.11 or newer is available.
- A headed/persistent browser runtime can be started for authenticated profiles.

Check live commands against the installed Hermes version:

```bash
hermes --version
hermes doctor
hermes gateway status
hermes cron status
hermes skills list
```

The official Hermes documentation is authoritative: <https://hermes-agent.nousresearch.com/docs>.

## 1. Clone and Install

```bash
cd /home/hermes
git clone https://github.com/jbellsolutions/event-lead-ops-agent.git event-lead-ops
cd event-lead-ops
python3.11 -m venv .venv  # or any verified Python >=3.11
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,browser]'
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest
```

If the host uses `uv`, an implementing agent may substitute `uv venv` and `uv pip install`, but it must still run the tests.

## 2. Create Runtime Directories

```bash
install -d -m 700 \
  /home/hermes/.local/share/event-lead-ops/secrets \
  /home/hermes/.local/share/event-lead-ops/browser-profiles/facebook \
  /home/hermes/.local/share/event-lead-ops/browser-profiles/craigslist \
  /home/hermes/.local/share/event-lead-ops/state \
  /home/hermes/.local/share/event-lead-ops/artifacts \
  /home/hermes/.local/share/event-lead-ops/logs
```

Do not store these directories under the Git checkout.

## 3. Create Local Configuration

```bash
cp config/business.example.yaml config/business.local.yaml
cp config/platforms.example.yaml config/platforms.local.yaml
cp config/scoring.example.yaml config/scoring.local.yaml
cp config/schedules.example.yaml config/schedules.local.yaml
```

Populate the real business details in the ignored `*.local.yaml` files. Keep both platforms in `observe` mode.

Use the host's service environment or secret manager for runtime paths. Never source raw browser cookie values through shell history.

## 4. Initialize State

```bash
.venv/bin/event-lead-ops \
  --db /home/hermes/.local/share/event-lead-ops/state/event-lead-ops.sqlite3 \
  init-db

.venv/bin/event-lead-ops \
  --db /home/hermes/.local/share/event-lead-ops/state/event-lead-ops.sqlite3 \
  status
```

## 5. Install the Hermes Skill

Install from the public raw URL using the command supported by the current Hermes version:

```bash
hermes skills install \
  https://raw.githubusercontent.com/jbellsolutions/event-lead-ops-agent/main/skills/event-lead-ops/SKILL.md \
  --name event-lead-ops
```

Then verify:

```bash
hermes skills list
```

Start a fresh Slack/Hermes session after skill changes so the skill index reloads.

## 6. Preserve Single Gateway Ownership

The existing Hermes Mac1 VPS remains the sole Slack gateway and scheduler owner. Verify there is not a second process using the same Slack Socket Mode credentials.

Do not copy Slack credentials into this repo. The project operates through the gateway already installed on the VPS.

## 7. Establish Browser Profiles

Follow `session-migration.md`. Recommended order:

1. Craigslist public observe lane (no account session)
2. Facebook persistent profile read-only certification
3. Craigslist account persistent profile certification
4. Draft-only flows
5. One approved external-write pilot per platform

Browser-login work is credential-bearing. Use a maintenance window and owner-only profile paths.

## 8. Create Bounded Cron Jobs

Use Hermes cron with `workdir=/home/hermes/event-lead-ops` so `AGENTS.md` is injected. Start with health only. Keep all collection schedules disabled until the corresponding live observe gate passes.

A self-contained health-job prompt:

```text
Operate the event-lead-ops project in read-only mode. Work from /home/hermes/event-lead-ops, load the event-lead-ops skill, run the deterministic status/health command against the configured database, report source state changes to the origin Slack thread, and take no external platform action. Do not schedule another cron job.
```

After certification, add one bounded source job at a time. Never install the entire daily business process as one large prompt.

## 9. Slack Verification

From the existing Hermes Mac1 Slack channel, ask:

```text
Load event-lead-ops and report status in read-only mode. Do not post or message anything.
```

The response must match the database and distinguish `unverified`, `healthy`, `blocked_auth`, and `paused` sources.

## 10. Production Promotion

Promotion is per source and per route:

```text
disabled -> observe -> draft -> approved_write
```

A browser version, egress, proxy, or profile migration change invalidates the previous certification and returns the source to `observe`.

## Rollback

- Pause the source cron jobs.
- Set source mode to `disabled`.
- Stop the source browser process without deleting its profile.
- Preserve the database and evidence for reconciliation.
- Revert the Git checkout to the last verified release.
- Restart the existing gateway only if gateway configuration changed.
