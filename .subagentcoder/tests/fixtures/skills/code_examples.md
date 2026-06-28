---
name: Error Handling
tags: [code]
description: Patterns for robust error handling and recovery.
---

# Error Handling Patterns

## Structured Error Types

Define explicit error types instead of relying on generic exceptions:

```python
class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation failed: {field} - {message}")
```

- Group errors by domain: validation, authentication, authorization, infrastructure
- MUST include enough context for debugging without leaking internals

## Retry Logic

Implement exponential backoff for transient failures:

```python
def retry_with_backoff(fn, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return fn()
        except TransientError:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
```

- NEVER retry on permanent failures (4xx client errors)
- ALWAYS set a maximum retry count to prevent infinite loops
- Log each retry attempt with the error details

## Graceful Degradation

Return partial results when non-critical dependencies fail:

```javascript
async function getUserProfile(userId) {
  const user = await userService.getById(userId); // critical
  let preferences = DEFAULT_PREFERENCES;
  try {
    preferences = await preferenceService.get(userId); // non-critical
  } catch (err) {
    logger.warn("Failed to load preferences, using defaults", { userId, err });
  }
  return { ...user, preferences };
}
```

- Distinguish between critical and non-critical dependencies
- MUST define sensible defaults for non-critical data
- Log degraded responses for monitoring
