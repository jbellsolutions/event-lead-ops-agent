# Operator Runbook

## Daily Start

1. Ask Hermes Mac1 for `status event lead ops`.
2. Review source health and certification age.
3. Run Craigslist/Facebook `observe` collection only after those collector CLI
   paths exist and have a current live certification; they are not shipped yet.
4. Review qualified opportunities.
5. Generate platform-specific drafts.
6. Approve only exact drafts intended for publication.
7. Review confirmation evidence after publishing.

## During the Day

- Poll responses no more frequently than configured.
- Review hot-inquiry alerts promptly.
- Approve, edit, or reject reply drafts.
- Pause a source immediately if account behavior looks abnormal.

## End of Day

- Reconcile database counts and successful actions.
- Review failed/ambiguous actions.
- Confirm no pending payment boundary. Automation never enters card data or
  confirms a charge; a payment screen requires human takeover or blocks the pilot.
- Produce the daily Slack report.

## Reauthentication

When a source is `blocked_auth`:

1. Pause schedules for that source.
2. Open the persistent VPS profile interactively or use the Mac recovery bridge.
3. Complete normal first-party authentication.
4. Do not bypass CAPTCHA or account warnings.
5. Run the read-only certification again.
6. Resume `observe` mode only.

## Ambiguous Submission

If a browser times out after clicking submit:

1. Do not retry.
2. Mark the action `needs_reconciliation`.
3. Inspect the operator's listings/ads and account dashboard.
4. Match title, timestamp, category, and other confirmation details.
5. Record `succeeded` or `failed` with evidence.
6. Only create a new proposed action if the original definitely failed.

## Emergency Pause

From Slack:

```text
pause facebook
pause craigslist
```

If Slack is unavailable, stop the corresponding bounded job/service on the VPS without deleting state or profiles.
