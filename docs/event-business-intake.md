# Event-Business Pilot Intake

The public repository cannot contain the operator's private business data or unapproved claims. Before draft generation, the implementing agent must collect and validate the following into ignored `config/*.local.yaml` files.

## Required Business Facts

- Legal/public business name
- Website and booking URL
- Contact email and phone intended for public listings
- Tampa Bay service center, radius, included and excluded locations
- Service hours and lead-response hours
- Insurance/licensing facts if relevant
- Accessibility and age restrictions if relevant

## First Offer

Choose exactly one offer for the first pilot:

- Offer name
- Event types served
- Included deliverables
- Explicit exclusions
- Starting price or approved `contact for quote` language
- Deposit/payment facts
- Availability facts
- Travel/setup fees
- Cancellation/refund policy
- Truthful differentiators
- Claims that must never be generated

Do not infer pricing, guarantees, capacity, availability, licensing, or social proof.

## Creative Assets

For each approved image/video:

- Runtime file path
- Rights/ownership confirmation
- People/model-release status when relevant
- Platform crop/order
- Alt description
- Expiration or campaign restriction

Do not commit production media unless the owner deliberately wants it public and has verified rights.

## Platform Decisions

### Craigslist

- Posting area
- Approved category/subcategory
- Whether the category is paid
- Maximum approved posts per day/week
- Duplicate/repost cooldown
- Contact/privacy choice
- Reply monitoring method

### Facebook Marketplace

- Listing type and category available to the account
- Tampa-area location and radius
- Price/availability fields
- Maximum approved listings per day/week
- Duplicate cooldown
- Approved listing images
- Inquiry monitoring scope

## Lead Discovery Decisions

- Positive intent keywords
- Negative/exclusion keywords
- Event type priorities
- Budget floor if any
- Service-area exclusions
- Seller/listing types never to contact
- Definition of hot, qualified, review, and archive

Discovery does not grant permission to contact a seller. Discovered opportunities enter a review queue.

## Response Decisions

- Public contact method
- Approved greeting/acknowledgment language
- Questions the agent may draft
- Questions requiring immediate escalation
- Words indicating urgency, payment, legal, safety, refund, or dispute risk
- Booking link and truthful next step

All replies are approval-gated in the initial MVP.

## Acceptance Record

The implementing agent records a redacted approval summary:

```text
Business config validated: yes/no
Offer ID: <stable ID>
Claims reviewed by: <operator identity>
Creative assets approved: <count>
Craigslist category/payment known: yes/no
Facebook listing category verified live: yes/no
External-write mode enabled: no (until platform pilot)
```

The default remains `observe` until the business facts, platform fields, and live browser contracts are verified.
