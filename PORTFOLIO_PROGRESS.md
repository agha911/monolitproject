# Portfolio preparation — stages 1–6

12 November 2026. Base: master / 628129e. Branch: codex/portfolio-readiness.

## Implemented

- Shared Telegram HMAC validation, timestamp expiry, duplicate-field rejection, and actor identity checks at the FastAPI application boundary.
- Legacy init_data parser now validates signatures. Invite handling uses the same parser instead of decoding untrusted JSON separately.
- Frontend attaches signed initData to all fetch calls targeting the configured API origin. Legacy body/query authentication is preserved and cross-checked.
- Shop admin activation now requires MONOLIT_ADMIN_KEY in addition to a signed user session. Existing partner and PvP admin endpoints retain their own secret validation.
- API base URL is configurable and defaults to localhost. Startup workers and Telegram lookups are opt-in. Production bot/debug handlers are not started by default.
- Full database URL and raw initData no longer logged; SQL echo disabled. This does not constitute a complete historical log audit.
- Frontend lockfile synchronized; TypeScript import, unused-variable and unsupported showToast errors fixed. Clipboard success uses supported haptic feedback.
- Backend schema initialization imports the full model registry. Missing task helper import and Windows tzdata dependency fixed.
- Local database Compose recipe, environment examples, README, development dependencies and GitHub Actions added.

## Verified locally

- Clean frontend dependency installation succeeds.
- Production frontend build succeeds (78 modules).
- TypeScript project check succeeds.
- 21 backend tests pass, covering signature validation, expiry, impersonation, conflicting credentials, admin access, and real-app startup/shutdown with background workers disabled.
- SQLAlchemy model registry configures successfully in the startup smoke test.
- The unauthenticated API returns 401 and health returns 200 without opening a database connection.

## Remaining

- The initial ESLint backlog was resolved in stage 5. Full lint now runs with zero warnings and is included in CI; the earlier stages below describe their historical checks.
- PostgreSQL 17 was found and a separate cluster was started on loopback port 55432. The schema and gameplay tests were exercised against isolated test schemas. The Docker recipe itself was not exercised locally.
- Still need migration strategy for existing databases and broader coverage of referrals, PvP completion/settlement, and partner workflows.
- A separate browser playground now exists in app.demo with synthetic players and a local demo signing token. Production app.main still requires real signed Telegram credentials. Demo is limited to clicks, rewards, upgrades and leaderboard, not all Telegram screens.
- Review remaining error responses and business-rule validation separately. This stage does not claim full production security or complete gameplay correctness.
- Stage 1 GitHub Actions passed. Stage 2 adds a PostgreSQL service to exercise integration tests remotely; its latest run is reported in the pull request.

No production deployment, real Telegram messages, production database access, or changes to the remote default branch were made during this stage.


## Stage 2 — implemented and verified

- Seven PostgreSQL integration scenarios: idempotent registration, duplicate click packets, concurrent daily claims, concurrent energy purchases, offer supply/balance, spending totals across different users, and PvP challenge daily limit.
- 30 tests pass locally, including guards that refuse a demo launch against a remote host or a database with another name.
- Fresh schema creation now creates league_enum; initialization output is Windows-console compatible.
- Daily claims lock the user row; spending statistics use an atomic PostgreSQL upsert to avoid lost updates.
- Gameplay progress response includes daily progress/target for the demo.
- Demo seeds three fictional players without wiping progress. Full original Telegram UI is preserved; VITE_DEMO_MODE selects a separate presentation screen.
- Browser verification: two taps added 20 points; reward increased balance by 50,000 and changed leaderboard rank; upgrade deducted 2,500 and increased capacity from 1,000 to 2,000. Verified narrow and wide layouts; screenshot: docs/portfolio-demo.jpg.
- Demo backend binds to 127.0.0.1:8000, frontend to 127.0.0.1:5173. Dedicated databases: monolit_demo and monolit_test. No real Telegram account, bot credentials, production database or paid service was used.

The demo is local only; public hosting, production migration, full feature verification, and existing lint cleanup remain unfinished.

## Stage 3 — referrals and PvP

- Added eight PostgreSQL integration scenarios covering first referral accrual, duplicate click packets, concurrent claims, expired referral cycles, PvP win/draw settlement, concurrent invitation acceptance, challenge ownership/replay, and expired matches.
- Referral accrual and claims now share a persisted cycle lock. Initializing the cycle preserves recent credits; empty claims return the response schema's supported status and persist cycle initialization.
- PvP invite acceptance and cancellation lock the invitation row, preventing two opponents from accepting the same invitation concurrently.
- Removed unnecessary pointer-event casts and fixed the demo effect dependencies. Targeted ESLint and TypeScript checks pass; the full legacy frontend lint backlog remains.
- All 38 backend tests pass locally against isolated schemas in monolit_test. No production data or default branch changed.

## Stage 4 — original interface in the browser demo

- Portfolio direction: preserve the original design and screens. `VITE_DEMO_MODE=true` now starts that interface after obtaining a synthetic, signed session from the isolated demo backend. The earlier simplified screen remains at `/playground` in demo mode.
- Central Telegram adapter leaves production on the real SDK. Demo mode supplies fictional identity and avoids Telegram sharing/invoice actions. Social subscription tasks and real user invitations show a demo notice instead of opening promotions.
- Added a DEMO notice and moved fixed profile/language controls below it. Fixed bottom navigation stacking so the coin no longer intercepts tab clicks on short screens.
- Fixed click-buffer lifecycle restoration after React StrictMode cleanup; browser checks confirmed a click was persisted and appeared in the Friends leaderboard.
- Browser checks: all five original tabs render; three fictional players load in the rankings; referral countdown loads; purchasing the 5,000-point booster reduced the balance from 59,591 to 54,591 and changed the multiplier to x2. Corrected purchase confirmation to use the returned level.
- TypeScript and targeted ESLint for the new adapter/notice/transport pass. Production build succeeds. Screenshot: docs/original-demo.jpg. Full legacy lint cleanup and exhaustive workflow testing remain unfinished; no public hosting was added.

## Stage 5 — frontend checks and API contract fixes

- Full frontend ESLint passes with zero warnings; npm run lint enforces that threshold and is now part of GitHub Actions. No lint rule was disabled or relaxed for this cleanup.
- Replaced explicit any types with player, match, leaderboard, configuration and error types in PvP, and typed referral/drop/task/UI state. Removed unused suppression directives and fixed effect dependencies. Extracted invite redirection from the entry point to its own component.
- Drop UI uses the server's user_left/disabled_for_user fields, refreshes offers after a purchase and no longer mutates an item in state or reads nonexistent remaining/user_remaining fields. It does not invent a global remaining count from total supply.
- Referral UI recognizes nothing_to_claim and no longer reports a payout when the server response is unreadable or lacks a confirmed amount. Demo popups display their message in the existing notice area.
- Extended the offer integration scenario to verify personal availability before/after purchase; this test passes on isolated PostgreSQL. Frontend lint, typecheck and production build pass locally.
- Browser PvP check completed: challenge starts, one tap is accepted and the final loss result is received without console errors. The result header now uses the server's snapshot of opponent_best_result, matching the target shown in the result card.
- Migration strategy, dependency hardening, further workflow coverage and public hosting remain open.

## Stage 6 — repeatable local package, publication deferred

- User selected preparation only, without publishing. No external hosting or paid resources were created.
- Added a multi-stage Dockerfile and a dedicated Compose recipe with an internal PostgreSQL service, a separate persistent volume and loopback-only web port. The application image runs as an unprivileged user; environment files and local credentials are excluded from its build context.
- Added app.demo_site to serve compiled original frontend routes/assets and the existing demo API on one origin. API lifespan still initializes/seeds the demo database. Missing API paths/assets return 404; health remains available at /health.
- Demo database guard still requires monolit_demo and the async PostgreSQL driver. An explicit container flag permits only the exact Compose hostname db in addition to loopback; arbitrary remote hosts remain rejected.
- Eight focused tests pass for SPA/API/assets/lifespan separation, missing builds and database configuration guards. The native compiled package and authenticated progress smoke check pass locally on port 8080.
- The complete local backend suite now has 44 passing tests.
- Docker is not installed locally. A new GitHub Actions job builds/starts the complete Compose package and runs the same smoke check; its result is reported with the PR.
- Runbook: docs/DEMO_RUNBOOK.md. Public exposure still requires a separate deployment configuration and demo isolation/session/request controls; this local package is not presented as ready for internet exposure.
