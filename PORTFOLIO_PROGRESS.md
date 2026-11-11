# Portfolio preparation — stage 1

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
- No PostgreSQL instance or Docker executable was available for full database gameplay verification. The Compose recipe and initialization procedure have not been exercised here.
- Need migration strategy for existing databases, seeded synthetic users, registration/shop/referral/PvP transaction tests, browser walkthrough and screenshots.
- Browser-only interactive demo is not implemented. Telegram gameplay requires a real development bot and signed initData; there is no insecure auth bypass.
- Review remaining error responses and business-rule validation separately. This stage does not claim full production security or complete gameplay correctness.
- CI configuration is prepared; a remote Actions run is not yet verified.

No production deployment, real Telegram messages, production database access, or changes to the remote default branch were made during this stage.
