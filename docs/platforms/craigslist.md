# Craigslist Adapter Contract

## Scope

Initial market: Tampa Bay. Public search discovery is read-only. Account posting and relay-response handling are separate authenticated capabilities.

## Read Collection Fields

Required:

- `external_id`
- `canonical_url`
- `title`
- `description`
- `category`
- `location`
- `posted_at`
- `price` when present
- image URLs when present
- reply-path type, not private relay contents
- evidence path/hash

## Collection Rules

- Use only configured search/category URLs.
- Bound pages per run and wait between requests.
- Prefer source IDs and canonical URLs over title-only dedupe.
- Treat sponsored/duplicate/reposted entries explicitly.
- Do not follow reply flows during discovery.
- Stop on rate limits, challenge pages, or contract failures.

## Posting Draft Contract

A Craigslist draft includes:

- Posting area and category
- Title
- Body
- Location
- Price if applicable
- Contact/privacy choices
- Images
- Fees shown by Craigslist
- Duplicate/cooldown result

The posting browser must stop before final submission until the immutable draft and any fee are approved.

## Response Monitoring

Prefer a verified account inbox or relay-email integration controlled by the operator. Dedupe by message/thread ID. Never expose relay addresses or raw private messages in Git or public dashboards.

## Live Acceptance

### Observe

- Configured Tampa result page loads.
- At least one valid result is normalized when results exist.
- Pagination stays within the configured limit.
- No account or reply action occurs.

### Approved write

- One approved synthetic/test campaign is submitted once.
- Platform ID/URL and confirmation evidence are captured.
- Account dashboard confirms state.
- A repeated execution request is blocked by idempotency.
