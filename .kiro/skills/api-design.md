---
name: API Design
tags: [code, api]
description: REST conventions, HTTP methods, status codes, response shapes, pagination.
---

# API Design

## Core Principle

APIs are contracts. They should be predictable, consistent, and hard to misuse. Design for the consumer, not the implementation.

## REST Conventions

### URLs
- Use nouns, not verbs: `/users`, `/orders`, not `/getUsers`, `/createOrder`
- Plural for collections: `/users`, `/users/{id}`
- Nest for ownership: `/users/{id}/orders` (orders belonging to a user)
- Keep URLs shallow — max 2 levels of nesting
- Use kebab-case for multi-word paths: `/user-profiles`, not `/userProfiles`

### HTTP Methods
- `GET` — read (safe, idempotent)
- `POST` — create (not idempotent)
- `PUT` — full replace (idempotent)
- `PATCH` — partial update (idempotent)
- `DELETE` — remove (idempotent)

### Status Codes
- `200` — success with body
- `201` — created (include Location header)
- `204` — success, no body (deletes, updates with no return)
- `400` — bad request (validation failed, malformed input)
- `401` — unauthenticated (no/invalid credentials)
- `403` — unauthorized (valid credentials, insufficient permissions)
- `404` — not found
- `409` — conflict (duplicate, state mismatch)
- `422` — unprocessable entity (valid syntax, semantic error)
- `500` — internal server error (never intentionally return this)

### Response Shape

Be consistent across all endpoints:

```json
{
  "data": { ... },
  "meta": { "page": 1, "total": 42 }
}
```

Error responses:
```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Email is required",
    "details": [{ "field": "email", "issue": "required" }]
  }
}
```

## Pagination

- Use `page` + `pageSize` (offset) or `cursor` (cursor-based)
- Always include total count or hasMore indicator
- Default page size should be reasonable (20-50) with a max cap
- Return pagination metadata in the response, not just headers

## Versioning

- Prefer URL path versioning: `/v1/users`, `/v2/users`
- Version when you make breaking changes
- Maintain old versions for a deprecation period
- Non-breaking additions (new optional fields) don't require a new version

## Input Validation

- Validate on receipt — before any business logic
- Return all validation errors at once, not one at a time
- Include field names and clear descriptions in error responses
- Apply sensible defaults for optional fields — document them

## General Rules

- Be consistent: if one endpoint returns `created_at`, all endpoints use `created_at` (not `createdAt` on some)
- Use ISO 8601 for dates: `2025-01-15T09:30:00Z`
- Use UTC for all timestamps
- Support filtering, sorting, and field selection on list endpoints
- Rate limit all endpoints — document the limits
- Include request IDs for tracing/debugging

## Anti-Patterns

- ❌ Verbs in URLs (`/getUser`, `/deleteOrder`)
- ❌ Returning 200 for errors with `{ "success": false }` in the body
- ❌ Different response shapes across endpoints
- ❌ Exposing internal IDs, database schemas, or implementation details
- ❌ Accepting unlimited input sizes (file uploads, array lengths, string lengths)
- ❌ Endpoints that do wildly different things based on query params
