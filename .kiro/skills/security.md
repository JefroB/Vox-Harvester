---
name: Security
tags: [code, security]
description: Input validation, auth, secrets management, injection prevention, dependencies.
---

# Security

## Core Principle

Security is a default, not a feature. Every input is untrusted, every output is a potential leak, every dependency is a liability.

## Input Validation

- Validate ALL external input: user forms, API params, file contents, environment variables, CLI args
- Validate type, length, range, and format
- Reject invalid input early — fail at the boundary, not deep in business logic
- Use allowlists over denylists when possible (accept known-good, not reject known-bad)

## Authentication & Authorization

- Never roll your own crypto or auth unless you're building an auth library
- Separate authentication (who are you?) from authorization (what can you do?)
- Check permissions on every request, not just at the UI layer
- Use constant-time comparison for secrets and tokens
- Expire sessions and tokens — nothing should live forever

## Secrets Management

- Never store secrets in source code or version control
- Use environment variables or dedicated secret stores
- Never log secrets, tokens, or passwords — even accidentally
- Rotate credentials regularly and on suspected compromise
- `.env` files must be in `.gitignore`

## Injection Prevention

- Use parameterized queries for SQL — never concatenate user input into queries
- Escape/sanitize output for the target context (HTML, shell, SQL, URLs)
- Use subprocess arrays over shell strings (avoid shell injection)
- Validate file paths to prevent directory traversal (`../../../etc/passwd`)

## Dependencies

- Pin exact versions — no floating ranges in production
- Audit dependencies for known vulnerabilities regularly
- Prefer well-maintained, widely-used packages over obscure ones
- If a dependency name looks unusual or could be typosquatting, verify it
- Minimize dependency count — each one is attack surface

## Data Protection

- Encrypt sensitive data at rest and in transit (TLS everywhere)
- Hash passwords with bcrypt, scrypt, or argon2 — never MD5/SHA for passwords
- Apply principle of least privilege: access only what's needed
- Sanitize error messages — don't expose stack traces, file paths, or internal state to users

## Common Pitfalls

- ❌ Trusting client-side validation alone (always re-validate server-side)
- ❌ Logging request bodies without redacting sensitive fields
- ❌ Using `eval()` or dynamic code execution on user input
- ❌ Hardcoding API keys "just for now"
- ❌ Disabling security features for convenience during dev and forgetting to re-enable
- ❌ Catching and silencing auth errors

## Checklist for New Features

1. What input does this accept? Is all of it validated?
2. What secrets does this use? Are they stored safely?
3. Who should be able to access this? Is that enforced?
4. What happens if a malicious user sends unexpected data?
5. Are error messages safe to show externally?
