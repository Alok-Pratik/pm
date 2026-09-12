# Code Review

Scope: no pending diff existed at review time (working tree clean, only
change against `origin/main` was a trailing-newline edit to `CLAUDE.md`), so
this review covers the full backend (`backend/app/*.py`) and the core
frontend (`frontend/src/components/*.tsx`, `frontend/src/lib/*.ts`).

The codebase is small (~1900 LOC) and generally solid. Prior work already
hardened concurrency: `write_connect()` uses `BEGIN IMMEDIATE` to serialize
writers against the `UNIQUE (column_id, position)` constraint, AI-driven
board operations are applied atomically, and chat's DB work is offloaded to
a thread so it doesn't block the event loop. The `KanbanBoard.tsx` reorder
math was checked against `@dnd-kit`'s standard `arrayMove` convention and is
correct.

Three findings survived review, all pre-existing rather than introduced by
recent changes:

## 1. SQLite connections are never explicitly closed

**File:** `backend/app/database.py:28-35`

`connect()` opens a new `sqlite3.Connection` on every call but nothing in
`main.py` ever calls `.close()` on it. The `with connect() as connection:`
pattern used throughout `main.py` only leans on `sqlite3.Connection`'s
context-manager protocol, which commits/rolls back the transaction on exit —
it does **not** close the connection or release its file descriptor.
Cleanup currently depends on CPython refcounting garbage-collecting the
object when it goes out of scope.

**Risk:** every request (`read_board`, `chat`, every mutation) opens a fresh
connection. Under sustained load, an exception path that keeps a traceback
alive, or a non-CPython interpreter without immediate refcounting, lets file
descriptors accumulate instead of being released deterministically — risking
"too many open files" or delayed lock release in this long-running
single-container server.

**Suggestion:** wrap connection use in a helper that explicitly closes on
exit (e.g. a small `contextlib.contextmanager` around `connect()` that
commits/rolls back and then calls `connection.close()`).

## 2. Card-creation logic is duplicated and has already drifted

**Files:** `backend/app/main.py:143-160` (REST `create_card`) vs.
`backend/app/database.py:216-232` (`apply_board_operations` /
`create_card` AI operation)

Both places independently reimplement "strip title, reject if empty, look
up column, count existing cards for position, insert." They have already
diverged: `main.py:154` generates `card-{secrets.token_hex(4)}` while
`database.py:226` generates `card-ai-{os.urandom(8).hex()}` for
AI-created cards.

**Risk:** a future rule change (title length limits, position semantics,
ID format) applied to one path and not the other leaves REST-created and
AI-created cards behaving inconsistently, since there's no single source of
truth for "create a card."

**Suggestion:** extract the shared insert logic (validate title, resolve
column, compute position, insert) into one `database.py` helper used by both
the REST endpoint and `apply_board_operations`.

## 3. Schema is re-initialized on every request

**File:** `backend/app/database.py:28-35`, `backend/app/main.py:36-39`

`connect()` unconditionally calls `initialize()`, which re-runs the full
`CREATE TABLE IF NOT EXISTS` / index script against `sqlite_master` — on
*every* call to `connect()`, i.e. every API request. `initialize()` is
already called once at startup in `main.py`'s `lifespan`.

**Risk:** no correctness issue (the script is idempotent), but every
board/chat/card request pays unnecessary parsing and I/O against
`sqlite_master` before doing any real work, for no benefit once the schema
exists.

**Suggestion:** drop the `initialize(connection)` call from `connect()` and
rely solely on the one-time call in `lifespan`.
