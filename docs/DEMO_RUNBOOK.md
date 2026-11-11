# Monolit demo package

Status: prepared for repeatable LOCAL runs. Publication is intentionally deferred.
The original interface is preserved. All accounts, points and actions belong to a dedicated demo database.

## Run with Docker Compose

Requirements: Docker Engine/Desktop with Compose. From the repository root:

```sh
docker compose -f compose.demo.yaml up --build --detach --wait
```

Open http://127.0.0.1:8080/. The multi-stage image builds the frontend in demo mode,
then serves it and the API from one origin using Python 3.12. PostgreSQL has no
published port; only the demo web port is bound to the host's loopback address.
The application runs as an unprivileged user. Real bot credentials are not needed.

Useful commands:

```sh
docker compose -f compose.demo.yaml ps
docker compose -f compose.demo.yaml logs --tail 100 demo
docker compose -f compose.demo.yaml down
```

Stopping with `down` preserves the named demo volume and player progress.
The package uses its own volume, separate from the development database recipe in `compose.yaml`.
The included database password is for this isolated local package only.

## Run without Docker (PowerShell)

Use the existing development dependencies and a local database named `monolit_demo`.
Build the frontend from `frontend/`:

```powershell
$env:VITE_DEMO_MODE='true'
$env:VITE_API_BASE_URL='/'
npm run build
```

Then, from `backend/`, using the project's Python environment:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://monolit@127.0.0.1:55432/monolit_demo'
python -m uvicorn app.demo_site:app --host 127.0.0.1 --port 8080
```

Adjust the database credentials/port to the dedicated local database. The entry
point refuses other database names and arbitrary remote hosts. `FRONTEND_DIST` can
override the compiled frontend directory. The Compose-only switch
`MONOLIT_DEMO_CONTAINER=true` additionally permits the exact internal hostname `db`;
it does not permit arbitrary remote hosts or other database names.

## Verify

- `/` loads the original home screen with a DEMO notice.
- `/tasks`, `/pvp` and `/playground` support direct browser navigation.
- `/health` exposes API health; `/demo/session` issues a synthetic session.
- API requests use the same origin and retain signed identity checks.
- Missing API routes/assets return 404 instead of the frontend HTML.

With the package running, from the repository root:

```sh
python scripts/check_packaged_demo.py
```

GitHub Actions builds and starts the Compose package and runs this smoke check.
It also runs backend regression tests and frontend lint, typecheck and build.
Local Docker execution has not been tested on the author's Windows machine because
Docker is not installed there; the native single-origin entry point is tested locally.

## Before a future public release

Select hosting separately. This local recipe must not simply be exposed by changing
the loopback binding. It currently shares one fictional player and uses an intentionally
known demo signing token. A public version needs controlled demo identities/session
isolation, request limits, restricted admin/partner routes, a separate database and
HTTPS configuration. Database migrations and a reset/retention policy also remain
deployment work. No hosting account, public endpoint or paid resource was created.
