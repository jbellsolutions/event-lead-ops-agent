# Facebook Marketplace Adapter Contract

## Scope

Initial market: Tampa Bay. Use one persistent browser profile and one authoritative owner. Read collection, listing publication, and inquiry monitoring are distinct capabilities.

## Session Health Assertions

A health check must assert:

- Marketplace—not a generic Facebook landing page—is loaded.
- The intended account is authenticated without printing its identity.
- Tampa location/search context is visible.
- No login checkpoint, CAPTCHA, account warning, or account-change prompt exists.
- The page contract is current.

Health checks must not open/create a listing, send a message, react, change settings, or dismiss a warning.

## Read Collection Fields

Required when visible:

- Marketplace listing ID
- Canonical URL
- Title
- Price
- Location
- Category/search context
- Posted/listed recency
- Image URLs or image count
- Seller alias only if it is publicly displayed and operationally necessary
- Evidence path/hash

Do not collect unrelated Messenger conversations or account data.

## Draft Contract

A Marketplace draft includes:

- Listing type
- Title
- Price
- Category
- Condition when required
- Description
- Tampa-area location
- Approved images
- Availability/delivery fields
- Duplicate/cooldown result
- Claims and risk flags

## Approved Publication

- Load the exact approved payload from the database.
- Stop on any changed field or new platform-required field.
- Fill fields without publishing.
- Revalidate the rendered preview.
- Submit once after the approval and execution lock are valid.
- Capture listing ID/URL and confirmation evidence.
- If submit state is uncertain, enter reconciliation; do not retry.

## Inquiry Monitoring

Only monitor conversations tied to operator-created Marketplace listings. Classify new messages and draft responses. Automatic replies remain disabled in the MVP.

## Live Acceptance

### Observe

- Persistent VPS profile passes the health assertions.
- A bounded Tampa search is normalized.
- No account mutation occurs.

### Approved write

- One approved test listing is published once.
- It appears in the operator's account.
- Confirmation evidence and platform ID are recorded.
- No warning or duplicate appears.
