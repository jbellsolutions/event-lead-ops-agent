# Facebook Marketplace Listing Draft

> Template only. Render from approved local business and campaign configuration.

## Immutable action fields

- Campaign ID: `{{ campaign_id }}`
- Listing type: `{{ listing_type }}`
- Category: `{{ category }}`
- Title: `{{ title }}`
- Price: `{{ price_display }}`
- Location: `{{ location }}`
- Condition/availability: `{{ condition_or_availability }}`
- Images in order: `{{ approved_image_paths }}`

## Description

{{ truthful_service_summary }}

Event types served:

{{ approved_event_types }}

Package includes:

{{ approved_deliverables }}

Service area: {{ approved_service_area }}

Next step: {{ approved_call_to_action }}

## Policy checks

- Persistent profile and route certified: `{{ route_certified }}`
- Account/category fields verified live: `{{ fields_verified }}`
- Business claims validated: `{{ claims_validated }}`
- Images rights validated: `{{ image_rights_validated }}`
- Duplicate cooldown passed: `{{ duplicate_check }}`
- Approval ID: `{{ approval_id }}`
- Payload hash: `{{ payload_hash }}`
