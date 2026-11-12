# Visitor-isolated demo candidate

Prepared for hosting review; nothing is published by these files.
The original Telegram interface is preserved. This is a separate entry point from
`app.main` (Telegram) and `app.demo_site` (the earlier shared local playground).

## Local preview

Using Docker Compose, from the repository root:

```sh
docker compose -f compose.demo.yaml -f compose.visitors.yaml up --build --detach --wait
python scripts/check_visitor_demo.py
```

Open http://127.0.0.1:8080/. Stop any earlier package on that port first.
This Compose project uses its own database volume and still binds only to loopback.
No Docker installation is needed for the native preview: build the frontend with
`VITE_DEMO_MODE=true` and `VITE_API_BASE_URL=/` as in DEMO_RUNBOOK.md, then run from
`backend/` with the project's Python environment:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://monolit@127.0.0.1:55432/monolit_demo'
$env:DEMO_PUBLIC_ORIGIN='http://127.0.0.1:8081'
python -m uvicorn app.public_demo:app --host 127.0.0.1 --port 8081 --workers 1 --no-proxy-headers --limit-concurrency 64
```

## Session and data boundaries

- `POST /demo/session` requires the exact configured Origin. A random HttpOnly,
  SameSite=Strict cookie is bound to that visitor's signed initData. On HTTPS the
  cookie is also Secure. A credential copied into another session does not work.
- The signing token is generated for the process and is never the known local-demo
  token or a real Telegram bot token.
- Each visitor receives a separate PostgreSQL schema containing three fictional
  players. Balances, rewards, rankings, purchases and challenge attempts are private
  to that schema, even though the fictional player IDs are the same.
- Sessions last 20 minutes. Reloading within that time resumes the same game;
  reloading after expiry creates a fresh one. The UI displays an expiry notice and
  a Reload button after an expired request.
- At most 12 sandboxes exist at once. Cleanup runs every 30 seconds and before
  allocation; in-flight requests retain their sandbox until they finish. Only
  generated `monolit_public_<32 hex digits>` schemas are eligible for deletion.
- Restarting resets visitor progress. Startup removes abandoned demo schemas under
  the same exact naming restriction. A PostgreSQL advisory lock enforces one worker
  and one replica, so another worker cannot delete active visitor sandboxes.
- The database must be the dedicated `monolit_demo`, on loopback or the explicitly
  enabled Compose hostname `db`. Do not use a production database. The role needs
  permission to create/drop schemas only in this disposable database.

## Allowed operations and resource limits

The server uses an exact method/path allowlist. The demo permits normal clicks,
virtual upgrades, daily rewards, check-in, referrals, private rankings and challenge
PvP. Administrator, partner redemption, real-offer purchase, social subscription,
governance mutation, live invitations and matchmaking routes are unavailable,
even with a valid visitor session. The UI explains that live invitations are off
and keeps Challenge mode available; partner promotions are not fetched in demo mode.

Current limits per process:

| Boundary | Limit |
| --- | --- |
| New sessions per peer IP | 3 / minute |
| Session bootstrap requests per peer IP | 12 / minute |
| API requests per session | 600 / minute |
| API + session requests, total | 2,400 / minute |
| Concurrent API requests per session | 8 |
| POST body | 16 KiB, including chunked input |
| Query string | 4 KiB |
| Body read timeout | 5 seconds |
| SQL statement / lock timeout | 5 seconds / 2 seconds |

Limiter bookkeeping is bounded. Overload returns 429 or 503 with Retry-After.
The Compose command also caps application concurrency at 64 and keep-alive at
5 seconds. These are small-demo limits, not a load-test or DDoS guarantee.

The gateway ignores forwarding headers; the supplied server command disables proxy
header trust. Behind a hosting proxy, visitors may initially share its peer-IP quota.
Select and configure a trusted proxy boundary when hosting is agreed; do not simply
trust arbitrary X-Forwarded-For values or enable multiple replicas.

Responses have a self-origin content policy, clickjacking protection, no-sniff and
no-referrer headers. API/session responses are not cached. HTTPS additionally enables
HSTS. Internal click-save errors return a generic 503 rather than exception text or
an apparent zero balance.

## Checks and remaining deployment work

Tests cover cross-visitor progress/reward isolation, cookie/credential binding,
capacity, expiry, active-request cleanup, a second worker, blocked routes, origin
validation, oversized/chunked bodies and limiter recovery/forwarding-header spoofing.
GitHub Actions also starts the full visitor Compose package and exercises two
independent HTTP cookie jars.

Before publishing, agree the host/cost and final HTTPS domain. Configure TLS, the
exact `DEMO_PUBLIC_ORIGIN`, dedicated database credentials/network access, proxy
trust/edge limits and process restart policy there. No hosting account, internet
endpoint, paid service or production change has been created. The legacy Telegram
application still needs its own migration/dependency/feature review before any
production release; this candidate is only for fictional portfolio play.
