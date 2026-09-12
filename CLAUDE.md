# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user Project Management MVP: a Kanban board with an AI chat sidebar. The frontend is a Next.js static export served by a FastAPI backend, all packaged into a single Docker container with a SQLite database. The AI uses OpenRouter with `nvidia/nemotron-3-ultra-550b-a55b:free`.

## Running the app

Requires a root `.env` file containing `OPENROUTER_API_KEY`.

```bash
./scripts/start.sh   # macOS/Linux — builds and starts Docker
./scripts/stop.sh    # stop
```

App is served at `http://localhost:8000`. Credentials: `user` / `password`.

## Backend commands

```bash
cd backend
uv sync --all-groups
uv run pytest                        # all tests
uv run pytest tests/test_foo.py      # single file
```

## Frontend commands

```bash
cd frontend
npm install
npm run dev          # local dev server (no Docker)
npm run lint
npm run test:unit    # Vitest
npm run test:e2e     # Playwright (requires Docker running)
npm run build        # static export to out/
```

For e2e tests against Docker: `PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 npm run test:e2e`

## Architecture

### Request flow

Browser → FastAPI (`:8000`) → SQLite (`/app/data/`) for board/auth, OpenRouter for AI.

The Next.js app is statically exported (`next build` → `out/`) and FastAPI mounts those files at `/`. There are no Next.js API routes or SSR — FastAPI is the sole server.

### Backend (`backend/app/`)

- `main.py` — FastAPI app, all routes under `/api/`: auth (`/api/auth/session`, `/api/auth/login`, `/api/auth/logout`), board (`/api/board`, `/api/columns/{id}`, `/api/cards`, `/api/cards/{id}`, `/api/cards/{id}/move`), chat (`/api/chat`, `/api/chat/history`)
- `database.py` — SQLite schema creation, seed data, all read/write helpers
- `ai.py` — structured AI response: builds prompt with full board JSON + bounded history (last 20 messages), validates and applies up to 20 board operations atomically
- `openrouter.py` — HTTP client for OpenRouter
- `config.py` — environment config (`OPENROUTER_API_KEY`)

Auth uses Starlette `SessionMiddleware` (itsdangerous-signed cookies). Every board and chat endpoint calls `signed_in_user()` to verify the session before touching the database. `SESSION_SECRET` is optional; if unset, a random per-process key is used, which invalidates existing sessions on restart.

### Frontend (`frontend/src/`)

- `components/KanbanBoard.tsx` — top-level board; loads `BoardData` from API, owns drag/drop via `@dnd-kit/core`
- `components/KanbanColumn.tsx` — droppable, renameable column
- `components/KanbanCard.tsx` — sortable, editable, removable card
- `components/ChatSidebar.tsx` — AI chat sidebar; sends requests to `/chat`, refreshes board from canonical response
- `components/AuthGate.tsx` — wraps the app; shows login form until session is confirmed
- `lib/api.ts` — all fetch calls to FastAPI (board, auth, chat)
- `lib/kanban.ts` — `BoardData` types, ordering/move helpers, client temp ID generator

Card order lives in `Column.cardIds`. FastAPI is the source of truth; UI state is updated from canonical API responses after every mutation.

### Database schema

Five tables: `users`, `boards` (one per user), `columns` (five fixed, renameable), `cards` (position-ordered per column), `chat_messages`. See `docs/DATABASE_SCHEMA.md` for full DDL.

### Docker build

Multi-stage: Node builds the frontend static export, then Python/uv installs the backend and copies in the built files. SQLite data persists in a named Docker volume (`pm_data`).

## Coding standards

- No over-engineering. No extra features. Keep it simple.
- No emojis ever.
- Identify root cause before fixing; prove with evidence.
- FastAPI only — never add Next.js API routes or SSR.
- OpenRouter key stays backend-only; never in frontend bundles, logs, or tests.
- Five fixed columns — count is immutable, only titles change.
- Add backend tests in `backend/tests/` for every endpoint or persistence behavior.
- Update frontend tests whenever UI behavior changes.

@docs/AGENTS.md