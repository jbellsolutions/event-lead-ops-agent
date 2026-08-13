# Agent Handoff

You have been given this repository to implement an approval-gated event-business lead-operations MVP on an existing always-on Hermes VPS.

## Your Assignment

1. Clone the repository and work from its root so `AGENTS.md` loads.
2. Run the release preflight and fix any failures before deployment.
3. Inspect `IMPLEMENTATION_STATUS.md`; do not claim unfinished live adapters are working.
4. Complete `docs/event-business-intake.md` with the operator and write facts only to ignored local configuration.
5. Run the five-round council in `docs/browser-execution-council.md` before any live browser workflow.
6. Follow `docs/implementation-plan.md` milestone by milestone.
7. Deploy into the existing Hermes Mac1 VPS and reuse its existing Slack app/gateway.
8. Keep Craigslist and Facebook in `observe` mode until their live read-only gates pass.
9. Keep all posting and replies approval-gated.
10. Build every writer so it retains the original execution reservation, calls
    `mark_action_submitting()` once immediately before platform submit, and uses
    only that call's immutable returned payload. Never submit from a proposal or
    caller-owned payload dictionary.
11. Report exact tests, live evidence, achieved counts, and blockers without exposing credentials.

## Start Here

```bash
git clone https://github.com/jbellsolutions/event-lead-ops-agent.git event-lead-ops
cd event-lead-ops
./scripts/deploy_preflight.sh
```

Then read, in order:

1. `AGENTS.md`
2. `IMPLEMENTATION_STATUS.md`
3. `docs/deployment.md`
4. `docs/event-business-intake.md`
5. `docs/browser-execution-council.md`
6. `docs/implementation-plan.md`
7. `docs/verification-contract.md`

## Completion Standard

A description or stub is not completion. The MVP needs real tool evidence for:

- Craigslist live observe collection
- Facebook persistent-profile observe collection or a grounded challenge blocker
- Database, dedupe, scoring, approval, audit, and idempotency paths
- Exact Slack status and approval workflow through Hermes Mac1
- One explicitly approved test post/listing per platform, or a documented live blocker
- Inquiry detection and approval-gated reply drafting
- VPS-owned bounded schedules and Mac-off control-plane behavior

Do not enable an external write simply because the code path exists. Certification and one exact approval are both required.
