# Portfolio preparation — stages 1 and 2

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

- Existing ESLint errors remain (many explicit any types, empty catches, React hook dependency warnings). Lint was run and is not green; it is not hidden by disabling rules or added as a falsely passing CI gate.
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
