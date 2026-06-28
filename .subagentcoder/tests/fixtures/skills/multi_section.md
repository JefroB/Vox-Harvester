---
name: API Design
tags: [code, api]
description: Guidelines for designing REST APIs.
---

# API Design Skill

Foundational patterns for building consistent REST APIs.

## Endpoint Naming

- Use plural nouns for resource collections: `/users`, `/orders`, `/products`
- Use kebab-case for multi-word resources: `/user-profiles`
- Nest sub-resources under their parent: `/users/{id}/orders`
- NEVER use verbs in endpoint paths — HTTP methods convey the action

## Request Validation

1. Validate all request parameters at the controller boundary
2. Return 400 Bad Request with a structured error body for invalid input
3. MUST reject unknown fields in strict mode
4. Use JSON Schema or equivalent for payload validation

### Error Response Shape

All validation errors SHOULD follow this shape:

```json
{
  "error": "validation_failed",
  "details": [{"field": "email", "message": "invalid format"}]
}
```

## Pagination

- ALWAYS support pagination on collection endpoints
- Use cursor-based pagination for large datasets
- Return `next_cursor` and `has_more` in response metadata
- Default page size SHALL be 20 items, maximum 100

## Authentication

- Use Bearer tokens in the Authorization header
- NEVER pass tokens as query parameters
- Return 401 Unauthorized for missing or expired tokens
- Return 403 Forbidden for valid tokens with insufficient permissions
