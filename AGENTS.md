

# Repository Guidelines

## Project Structure & Module Organization
`backend/` contains the FastAPI app, Celery worker, Alembic migrations, and utility scripts such as `import_local.py` and cleanup tools. Core API code lives under `backend/app/` with `api/`, `models/`, `services/`, `core/`, and `worker/`. `frontend/` is a Vite + React + TypeScript client; pages are in `frontend/src/pages/`, shared layout components in `frontend/src/components/layout/`, and API/state helpers in `frontend/src/services/` and `frontend/src/store/`. `bot/` and `telethon_manager/` are separate Python services. Runtime orchestration is defined in `docker-compose.yml`.

## Build, Test, and Development Commands
Use Docker for integrated development:

- `docker compose up -d` starts the full stack.
- `docker compose build backend frontend` rebuilds the services that changed.
- `docker compose up -d backend frontend` restarts rebuilt app containers.
- `docker compose exec backend alembic upgrade head` applies DB migrations.
- `docker compose exec backend pytest` runs backend tests when present.

For frontend-only work:

- `cd frontend && npm install` installs dependencies.
- `cd frontend && npm run dev` starts the Vite dev server.
- `cd frontend && npm run build` runs TypeScript compilation and produces a production build.

## Coding Style & Naming Conventions
Python uses 4-space indentation, snake_case for functions/modules, and type-aware FastAPI service structure. Keep new backend logic inside the existing domain folders instead of adding standalone scripts unless the task is operational. Frontend code uses TypeScript, 4-space indentation, single quotes, and PascalCase component files such as `DashboardPage.tsx`. Follow existing naming like `authStore.ts` for Zustand stores and `api.ts` for transport helpers.

## Testing Guidelines
`pytest` is available in `backend/requirements.txt`, but the repository currently has little or no committed test coverage. Add backend tests near the feature they validate or under a new `backend/tests/` package, and name files `test_<feature>.py`. For frontend changes, at minimum verify `npm run build` and exercise the affected screen against the running Docker stack.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commit subjects such as `Add Telethon account ingestion workflow` and occasional `feat:` prefixes. Prefer one clear subject line per change; keep it under about 72 characters. PRs should describe the user-visible impact, list any migration or container rebuild steps, link related issues, and include screenshots for frontend changes.

## Security & Configuration Tips
Secrets belong in `.env`; do not hardcode database credentials or tokens in source or compose files. If you change backend dependencies or startup behavior, rebuild the backend image instead of relying on `docker compose restart`.
