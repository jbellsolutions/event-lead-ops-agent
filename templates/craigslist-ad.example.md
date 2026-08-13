# Craigslist Ad Draft

> Template only. Render from approved local business and campaign configuration.

## Immutable action fields

- Campaign ID: `{{ campaign_id }}`
- Posting area: `{{ posting_area }}`
- Category: `{{ category }}`
- Fee shown by platform: `{{ fee_display }}`
- Title: `{{ title }}`
- Location: `{{ location }}`
- Price: `{{ price_display }}`
- Contact/privacy choice: `{{ contact_method }}`
- Images: `{{ approved_image_paths }}`

## Body

{{ truthful_service_summary }}

Good fit for:

{{ approved_event_types }}

What is included:

{{ approved_deliverables }}

Service area: {{ approved_service_area }}

Next step: {{ approved_call_to_action }}

## Policy checks

- Business facts loaded from ignored local config: `{{ facts_validated }}`
- Category verified live: `{{ category_verified }}`
- Fee approved: `{{ fee_approved }}`
- Claims validated: `{{ claims_validated }}`
- Images rights validated: `{{ image_rights_validated }}`
- Duplicate cooldown passed: `{{ duplicate_check }}`
- Approval ID: `{{ approval_id }}`
- Payload hash: `{{ payload_hash }}`
