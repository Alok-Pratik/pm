# Code Review

Full review of the codebase as of the completed MVP (all 10 parts done).
Organised by severity. Each item lists the file/line and a concrete action.

## Previous review status

The earlier review's 20 findings were re-checked against the current code:

- **Fixed:** stale card edit state, dirty cancel, orphaned optimistic chat
  message, `rename_column` ownership, chat message length limit,
  type-discriminated `BoardOperation` validation, proper AI message turns
  instead of a JSON blob, stable `onUnauthorized` callback, column card
  children no longer remount, 422 validation tests, DnD browser test,
  component unit tests, and failed-login/session-expiry e2e tests.
- **Still present (reassessed below):** the AI-call race window, duplicate
  move-card logic, and schema init on every connection.

## Bugs

### 1. AI operations can persist blank column and card titles
**File:** `backend/app/database.py:199-213`, `backend/app/ai.py:8-19`

`apply_board_operations` calls `op.title.strip()` for `rename_column` and
`create_card` but never rejects an empty result, so the AI can save a blank
column title or a blank card title. The interactive REST endpoints enforce a
non-blank title (`main.py:133-136, 147-149`), so AI and manual flows behave
differently.

**Fix:** Add a non-blank-title check in `apply_board_operations` for
`rename_column` and `create_card` (raise `ValueError` like `edit_card` does),
or add `min_length=1` plus strip validation to the Pydantic models.

### 2. Concurrent card creation can 500
**File:** `backend/app/main.py:154-161`, `backend/app/database.py:206-213`

New-card `position` is computed as `SELECT COUNT(*)` from the same column, then
inserted against the `UNIQUE (column_id, position)` constraint. Two concurrent
creates in the same column read the same count first; the loser either hits
`IntegrityError` on insert or `database is locked`, surfacing as a 500.

**Fix:** Serialize writes for the MVP (e.g., `BEGIN IMMEDIATE`, or retry on
`IntegrityError`). Low likelihood for a single user, but the crash is not
handled gracefully today.

### 3. Arrow keys while editing a card can start a drag
**File:** `frontend/src/components/KanbanCard.tsx:44-56`

`useSortable` spreads its listeners (including keyboard activation) on the
card `<article>`. The edit form stops `onPointerDown` propagation but not
`keydown`, so pressing arrow keys inside the title/details inputs can trigger
a dnd-kit keyboard drag mid-edit.

**Fix:** Stop `keydown` propagation on the edit form (`onKeyDown={(e) => e.stopPropagation()}`).

### 4. Card editor closes even when the save request fails
**File:** `frontend/src/components/KanbanCard.tsx:50-56`,
`frontend/src/components/KanbanBoard.tsx:97-99`

The form calls `onEdit(...)` and immediately `setIsEditing(false)` while
`handleEditCard` fires `apply(api.updateCard(...))` without awaiting it. If
the request fails, the user's typed input is lost along with the error shown
only at the board level.

**Fix:** Pass the pending promise back and only close the editor on success
(or keep the inputs populated so the user can retry).

## Minor issues

### 5. `/api/hello` is leftover scaffolding
**File:** `backend/app/main.py:100-102`

Part-2 example endpoint still deployed. No caller exists.

**Fix:** Delete the route.

### 6. `moveCard` and its helpers in `lib/kanban.ts` are dead code
**File:** `frontend/src/lib/kanban.ts:21-106`

`KanbanBoard` computes the target position inline (`KanbanBoard.tsx:80`) and
updates solely from the backend-canonical board. `moveCard`, `isColumnId`, and
`findColumnId` are exercised only by their unit test.

**Fix:** Remove them (and the test) or wire the UI through the helper so
drag-move logic lives in one place.

### 7. Drag-and-drop can only insert a card before another card
**File:** `frontend/src/components/KanbanBoard.tsx:80`

Position is derived from `indexOf(overId)`, which always places the dropped
card *before* the hovered card in another column; dropping after a card is
never possible. Same-column drops happen to land after the target via the
remove-then-insert order, so behaviour is inconsistent between columns.

**Fix:** Compute the insert index from the drop midpoint within the over target
or document the "insert before" behaviour as intended.

### 8. Session secret is a known constant in the container
**File:** `backend/app/main.py:29,42-47`, `docker-compose.yml`

`SESSION_SECRET` is not passed through `docker-compose.yml`, so the container
runs with the hardcoded `local-development-secret` while only logging a
warning.

**Fix:** Pass `SESSION_SECRET` from the root `.env` (optional) and document it,
or accept the warning for a local-only MVP. The warning is good; the default
should not be silent in the shipped image.

### 9. Schema init runs the full DDL on every connection
**File:** `backend/app/database.py:28-35, 38-66`

`connect()` calls `initialize()` on every request, re-running
`CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS`, which also performs
an implicit `COMMIT` via `executescript`.

**Fix:** Keep as-is for MVP simplicity, or gate the DDL behind a single
startup check (the `lifespan` handler already calls `initialize`).

### 10. Blocking SQLite work inside an async endpoint
**File:** `backend/app/main.py:210-244`

`chat` is `async def` but performs synchronous `sqlite3` reads and writes
inline, blocking the event loop while disk I/O happens.

**Fix:** For MVP this is acceptable at single-user scale; if concurrent usage
appears, move the DB work into a thread (`run_in_executor`) or make the route
sync like the others.

### 11. Seed data duplicated between frontend and backend
**File:** `frontend/src/test/fixtures.ts`, `backend/app/database.py:16-25`

The same five columns and eight cards exist in both places. Any seed change
requires editing two files and can silently desynchronise tests.

**Fix:** Derive the frontend fixture from the backend's canonical `/api/board`
response, or generate it from the same source of truth.

### 12. OpenRouter request lacks `response_format` and `max_tokens`
**File:** `backend/app/openrouter.py:20-29`

No structured-output hint or token cap. Markdown-fenced model output (which the
prompt already forbids) fails `parse_ai_response` and surfaces as an opaque 502
to the user.

**Fix:** Set `max_tokens` and, if the selected model supports it, pass a
JSON-oriented `response_format`.

### 13. Chat history load swallows non-401 errors
**File:** `frontend/src/components/ChatSidebar.tsx:18-22`

Only `ApiError` with status 401 is handled; any other failure leaves the
sidebar silently empty.

**Fix:** Surface a readable error message on non-401 failures, matching the
board's error handling.

### 14. Rename input remounts after each saved rename
**File:** `frontend/src/components/KanbanColumn.tsx:51`

`key={`${column.id}-${column.title}`}` recreates the input whenever the saved
title changes, dropping focus after a rename commits.

**Fix:** Drop the `key` and rely on `useEffect` state sync, so focus survives.

### 15. Docker reproducibility nits
**File:** `Dockerfile:11,19-20`

`ghcr.io/astral-sh/uv:latest` is unpinned, and `backend/uv.lock` is not copied
into the build, so the Python layer re-resolves dependencies.

**Fix:** Pin the uv image tag and `COPY backend/uv.lock ./` alongside
`pyproject.toml`, then `uv sync --no-dev --locked`.

## Testing gaps

- No backend test covers blank AI column/card titles — the gap that let bug
  #1 through.
- Playwright's "move between columns" tests call `/api/cards/{id}/move`
  directly; only the within-column reorder exercises the real pointer drag.
  A real cross-column drag test would cover bug #7-style behavior.

## Summary

The implementation is solid: atomic AI operations, canonical board responses,
ownership-verified SQL, proper Pydantic/discriminated-union validation, and
meaningful unit, integration, and browser coverage. The remaining issues are
mostly low-severity robustness and UX items; the two worth fixing soon are the
AI blank-title validation gap (#1) and the card-save/error handling (#4).