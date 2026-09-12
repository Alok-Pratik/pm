# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A multi-user Project Management application: each user registers/logs in with their own account and owns any number of Kanban boards, each with an AI chat sidebar scoped to that board. The frontend is a Next.js static export served by a FastAPI backend, all packaged into a single Docker container with a SQLite database. The AI uses OpenRouter with `nvidia/nemotron-3-ultra-550b-a55b:free`.

Every user's boards, columns, cards, and chat history are private to that user — no cross-user access to another user's data under any endpoint.

## Running the app

Requires a root `.env` file containing `OPENROUTER_API_KEY`.

```bash
./scripts/start.sh   # macOS/Linux — builds and starts Docker
./scripts/stop.sh    # stop
```

App is served at `http://localhost:8000`. Register a new account from the login screen, or sign in with an existing one.

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

- `main.py` — FastAPI app, all routes under `/api/`: auth (`/api/auth/register`, `/api/auth/session`, `/api/auth/login`, `/api/auth/logout`), boards (`/api/boards` list/create, `/api/boards/{board_id}` get/rename/delete), board contents (`/api/boards/{board_id}/columns/{id}`, `/api/boards/{board_id}/cards`, `/api/boards/{board_id}/cards/{id}`, `/api/boards/{board_id}/cards/{id}/move`), chat (`/api/boards/{board_id}/chat`, `/api/boards/{board_id}/chat/history`)
- `database.py` — SQLite schema creation, seed data, all read/write helpers
- `ai.py` — structured AI response: builds prompt with the target board's JSON + bounded history (last 20 messages), validates and applies up to 20 board operations atomically
- `openrouter.py` — HTTP client for OpenRouter
- `config.py` — environment config (`OPENROUTER_API_KEY`)

Auth uses Starlette `SessionMiddleware` (itsdangerous-signed cookies) plus hashed passwords (e.g. `passlib`/`bcrypt`) stored in `users`. Every board, board-contents, and chat endpoint calls `signed_in_user()` to verify the session, then verifies that the requested `board_id` is owned by that user before touching any row under it. `SESSION_SECRET` is optional; if unset, a random per-process key is used, which invalidates existing sessions on restart.

### Frontend (`frontend/src/`)

- `components/BoardSwitcher.tsx` — lists the signed-in user's boards; create, rename, delete, and switch between them
- `components/KanbanBoard.tsx` — top-level board for the selected `board_id`; loads `BoardData` from API, owns drag/drop via `@dnd-kit/core`
- `components/KanbanColumn.tsx` — droppable, renameable column
- `components/KanbanCard.tsx` — sortable, editable, removable card
- `components/ChatSidebar.tsx` — AI chat sidebar scoped to the selected board; sends requests to `/boards/{board_id}/chat`, refreshes board from canonical response
- `components/AuthGate.tsx` — wraps the app; shows login/register form until session is confirmed
- `lib/api.ts` — all fetch calls to FastAPI (auth, boards, board contents, chat)
- `lib/kanban.ts` — `BoardData` types, ordering/move helpers, client temp ID generator

Card order lives in `Column.cardIds`. FastAPI is the source of truth; UI state is updated from canonical API responses after every mutation.

### Database schema

Five tables: `users` (hashed passwords), `boards` (any number per user, ownership via `boards.user_id`), `columns` (five fixed per board, renameable), `cards` (position-ordered per column), `chat_messages` (scoped to a `board_id`). See `docs/DATABASE_SCHEMA.md` for full DDL — keep it in sync with `database.py`.

### Docker build

Multi-stage: Node builds the frontend static export, then Python/uv installs the backend and copies in the built files. SQLite data persists in a named Docker volume (`pm_data`).

## Coding standards

- No over-engineering beyond the multi-user/multi-board scope above. Don't add features outside it (no teams, roles/permissions, sharing, or invites) unless asked. Keep it simple.
- No emojis ever.
- Identify root cause before fixing; prove with evidence.
- FastAPI only — never add Next.js API routes or SSR.
- OpenRouter key stays backend-only; never in frontend bundles, logs, or tests.
- Passwords are always hashed at rest; never log or return password values.
- Five fixed columns per board — count is immutable, only titles change.
- Every board-scoped endpoint must verify the signed-in user owns `board_id` before reading or writing anything under it.
- Add backend tests in `backend/tests/` for every endpoint or persistence behavior, including cross-user isolation (user A cannot read/write user B's boards, columns, cards, or chat history) and multi-board behavior for a single user.
- Update frontend tests whenever UI behavior changes.
- Maintain strong backend test coverage with integration tests (real DB, real routes) in addition to unit tests, run via `uv run pytest`.