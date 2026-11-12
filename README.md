# Monolit

A Telegram Mini App with a React/TypeScript frontend and a FastAPI/PostgreSQL backend. Features include a clicker with energy recovery, daily tasks, referrals, a virtual-currency shop, partner offers, PvP matches, and Azerbaijani/Russian/English localization.

## Portfolio preparation status

The portfolio demo uses the original Telegram interface with synthetic players and a browser demo session. Home, tasks, friends, shop and PvP screens use real local backend operations. A small DEMO notice identifies the fictional data; Telegram sharing, social subscription tasks and payments are unavailable. No production database or bot should be used for development.

![Original interface in browser demo mode](docs/original-demo.jpg)

## Browser playground

For a compiled frontend and API on one local address, see the [demo package runbook](docs/DEMO_RUNBOOK.md). It includes a dedicated Docker Compose recipe and a native launch option. Public hosting is intentionally deferred.

The [visitor-isolated demo candidate](docs/VISITOR_DEMO.md) adds private temporary games, cookie-bound sessions, route restrictions and traffic limits for the next hosting review. It has a separate local preview; hosting and HTTPS configuration are still to be agreed.

Create a separate local PostgreSQL database named `monolit_demo`. The Compose recipe below creates one. Install backend and frontend dependencies as described in Local setup.

Start the backend from `backend/` with a dedicated loopback `DATABASE_URL` and `python -m uvicorn app.demo:app --host 127.0.0.1 --port 8000`. For the Compose database use `postgresql+asyncpg://monolit:local_demo_only@127.0.0.1:5432/monolit_demo`. The demo entry point refuses non-loopback hosts and other database names, disables bot/notification workers, uses a dedicated non-secret demo signing token, and seeds three fictional players without deleting existing demo progress. Do not expose this entry point publicly.

Start the frontend from `frontend/` with `VITE_DEMO_MODE=true` and `npm run dev`. In PowerShell set the variable first with `$env:VITE_DEMO_MODE='true'`; in bash use `VITE_DEMO_MODE=true npm run dev`. Visit the local URL printed by Vite. The API URL defaults to `http://127.0.0.1:8000`.

Try the original Home, Tasks, Friends, Shop and PvP tabs. Progress is persisted in the isolated demo database. The demo session lasts one hour; reload the page to obtain a fresh one. These points have no monetary value. The earlier simplified playground remains available at `/playground` in demo mode only. This does not claim every game workflow has been verified end to end.

For the original Telegram frontend, leave `VITE_DEMO_MODE` unset and use `app.main:app` with a real **development** bot.

## Local setup

Prerequisites: Python 3.11 or 3.12, Node.js 20+, and PostgreSQL 16 (or Docker Compose). Python 3.13 is not supported by the currently pinned database driver. Local checks were run on Python 3.12 and Node.js 22.

1. Start an isolated database: `docker compose up -d db` (or provision a separate PostgreSQL database).
2. Copy `backend/.env.example` to `backend/.env`. Set credentials for the **test** database and a separate development bot. The placeholder token is only sufficient for imports and local authentication tests; it does not enable Telegram login.
3. Create a virtual environment and install `backend/requirements-dev.txt`.
4. From `backend/`, run `python -m app.init_db` against the empty development database, then `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
5. Copy `frontend/.env.example` to `frontend/.env`. From `frontend/`, run `npm ci`, then `npm run dev -- --host 127.0.0.1`.
6. For actual gameplay, configure a development HTTPS frontend URL in your test bot's Mini App settings and use a separately hosted/tunnelled development backend. Configure its exact frontend origin in `CORS_ORIGINS`; never point this setup at production.

Database initialization is for a **fresh test database**. It does not migrate an existing schema. Production migration scripts and seeded demonstration scenarios remain follow-up work.

## Authentication

Frontend API requests attach `X-Telegram-Init-Data`. The backend validates the Telegram HMAC, rejects duplicate fields, and accepts credentials for one hour (30 seconds of future clock skew allowed). Reopen the Mini App to refresh an expired session. Legacy body/query `init_data` is still supported but must also be signed and current. Actor IDs in body, query, or `X-Telegram-User-Id` must match the validated identity. The legacy task `user_id` is a Telegram ID, not a database ID.

The three partner endpoints `/api/partner/purchases`, `/redeem`, `/revoke` retain their own `X-Partner-Key` authentication. The two PvP admin endpoints retain their `PVP_ADMIN_KEY` validation. All other `/api/` endpoints require Telegram authentication, including read-only ones. `/` is a public health endpoint; `/ping-db` is a database connectivity check.

Shop admin activation additionally requires `X-Admin-Key` matching `MONOLIT_ADMIN_KEY`. An empty key disables this action.

## Background jobs

All background features default to off. Enable only explicitly:

- `ENABLE_BOT_POLLING=true`: Telegram bot polling and delivery handlers. Run one polling process only.
- `ENABLE_NOTIFICATIONS=true`: energy notifications and notification-flag reset.
- `ENABLE_SEASON_WORKER=true`: periodic weekly season rollover. Season API reads may also run rollover as part of existing application logic.
- `ENABLE_HISTORICAL_FINALIZER=true`: historical September 2025 winner snapshot. Leave off for normal development.
- `ALLOW_TELEGRAM_LOOKUPS=true`: allow registration/PvP profile lookups through Telegram.

These settings control startup workers, not all database writes made by gameplay endpoints. Keep the development database isolated.

## Checks

From `backend/`: `python -m pytest tests -q`.

From `frontend/`: `npm run build`, `npm run typecheck`, `npm run lint`.

Authentication/startup tests do not contact Telegram or a database. To include PostgreSQL integration tests, set `TEST_DATABASE_URL` to a loopback PostgreSQL database named `monolit_test`. Each integration test creates and drops only its own randomly named schema. The suite checks registration, duplicate click packets, concurrent daily claims, concurrent purchases, offer supply, spending totals, and PvP daily limits. Without the variable, these integration tests are explicitly skipped. GitHub Actions provisions PostgreSQL and runs them.

Frontend ESLint now passes with zero warnings and runs in CI alongside TypeScript and the production build. Additional gameplay/database regression coverage, migration scripts, dependency hardening and public demo hosting remain part of portfolio preparation. See `PORTFOLIO_PROGRESS.md` for verified results and limitations.

## Layout

- `backend/app/main.py`: FastAPI composition, legacy gameplay routes and optional workers.
- `backend/app/auth.py`: shared Telegram authentication and actor identity checks.
- `backend/app/routers`, `crud`, `models`: API, business operations, SQLAlchemy models.
- `frontend/src/main.tsx`: frontend entry point; `components/ui`: screens.
- `frontend/src/apiFetch.ts`: shared authentication transport for legacy fetch calls.

Validation follows the [official Telegram Mini App specification](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
