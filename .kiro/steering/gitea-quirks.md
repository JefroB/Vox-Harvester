---
inclusion: always
---

# Gitea Server Quirks

## Push Requires Two Attempts

The local Gitea server at `192.168.1.25:3000` has a known behavior where the first `git push` will fail with an authentication error. The second attempt always succeeds.

**Rule:** When pushing to Gitea, always attempt the push twice. If the first push fails with an auth/verify error, immediately retry the same command. Do not ask the user about credentials or tokens — just push again.

## Server Details

- URL: http://192.168.1.25:3000
- User: Jefro
- Protocol: HTTP (not SSH)
