# Security Policy

## Secrets

This repository must never contain:

- Browser cookie exports
- Persistent browser profile directories
- Slack bot/app tokens
- Hermes `.env` or `auth.json`
- SSH keys
- Proxy credentials
- Platform passwords or recovery codes
- Payment/card data
- Customer or prospect exports
- Raw Messenger, Craigslist relay, or Slack archives

Use the target host's secret manager or owner-only runtime files (`0600`) outside the repository.

## Runtime Layout

Recommended:

```text
/home/hermes/.local/share/event-lead-ops/
├── secrets/          # 0700 directory; 0600 files
├── browser-profiles/ # 0700; never archived without encryption
├── state/            # database and cursors
├── artifacts/        # screenshots/evidence with retention limits
└── logs/             # redacted structured logs
```

## Reporting a Vulnerability

Do not open a public issue containing credentials, private account details, or customer data. Contact the repository owner privately through GitHub.

## Agent Safety

- Read-only browser health tests precede external writes.
- CAPTCHA, account checkpoints, rate limits, platform warnings, or unexpected payment screens fail closed.
- A Slack approval is scoped to the exact hash of one action payload and expires.
- External actions are idempotent and auditable.
- Proxy or browser-profile changes require a new read-only certification.
- No code in this repository is intended to bypass access controls or platform enforcement.
