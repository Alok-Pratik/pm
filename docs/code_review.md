# Code Review

Full review of the codebase as of the completed MVP (all 10 parts done). Organised by severity. Each item includes the file/line and a concrete action.

---

## Bugs

### 1. `KanbanCard` edit state goes stale after external board update
**File:** `frontend/src/components/KanbanCard.tsx:15-16`

`title` and `details` are initialised once from props via `useState`. When the board is refreshed (after an AI operation or another user action), the `card` prop updates but the local state does not re-initialise. If the user then opens the edit form they see old values; submitting overwrites the server's version.

**Fix:** Sync state from the current prop when opening edit mode:
```tsx
onClick={() => { setTitle(card.title); setDetails(card.details); setIsEditing(true); }}
```

---

### 2. Cancel button leaves dirty edit state
**File:** `frontend/src/components/KanbanCard.tsx:49`

`onClick={() => setIsEditing(false)}` does not reset `title`/`details`. After typing and clicking Cancel, reopening the edit form shows whatever the user had typed, not the saved values.

**Fix:** Reset state on cancel:
```tsx
onClick={() => { setTitle(card.title); setDetails(card.details); setIsEditing(false); }}
```

---

### 3. Optimistic user message orphaned on chat error
**File:** `frontend/src/components/ChatSidebar.tsx:31`

The user message is appended to the messages list before the API call. On failure, the error banner appears but the message stays with no assistant reply — a dangling half-conversation that persists for the session.

**Fix:** On catch, remove the last message before setting the error:
```tsx
setMessages((current) => current.slice(0, -1));
setError(...);
```

---

### 4. `rename_column` calls `get_board` without `user_id`
**File:** `backend/app/main.py:107`

```python
return get_board(connection)   # defaults to user_id="user"
```

Every other mutating endpoint passes `user_id` explicitly. This silently serves the wrong board if a second user is ever added.

**Fix:** `return get_board(connection, signed_in_user(request))`

---

### 5. Chat endpoint opens two separate DB connections with a race window
**File:** `backend/app/main.py:176-197`

The board is loaded on one connection (closed), the AI call is made, then a second connection applies operations. The AI's decisions are based on board state that is already stale by the time the second connection runs. For the current single-user MVP this is harmless, but it is structurally wrong.

**Fix:** Acquire a single connection before the AI call, pass it to `get_board` and `recent_chat_messages`, keep it open across the AI call, then apply operations and save history on the same connection.

---

## Security

### 6. `SESSION_SECRET` falls back to a known string with no warning
**File:** `backend/app/main.py:15`

```python
secret_key=os.environ.get("SESSION_SECRET", "local-development-secret")
```

A deployment that omits the env var silently uses a publicly-known signing key. Session cookies can be forged.

**Fix:** Raise at startup if the key is absent (or is the default), or at minimum log a loud warning. Add `SESSION_SECRET` to the `.env` template with a generated value.

---

### 7. No chat message length limit
**File:** `backend/app/main.py:170-172`

The only validation on `/api/chat` is that the message is non-empty. An arbitrarily long message is forwarded to OpenRouter, risking unexpected costs or upstream errors.

**Fix:** Add a max-length check (e.g. 2 000 characters) and return 422 if exceeded.

---

## Code Quality

### 8. Duplicate move-card logic
**Files:** `backend/app/main.py:149-167` and `backend/app/database.py:180-196`

The position-rewrite logic (remove from source column, insert into target column, call `rewrite_positions`) is nearly identical in both `move_card` and `apply_board_operations`. A bug fix in one does not automatically fix the other — already diverged slightly in minor structure.

**Fix:** Extract a `_move_card_in_db(connection, card_id, column_id, position, user_id)` helper in `database.py` and call it from both sites.

---

### 9. `board_for_user` called 3-4 times per request
**File:** `backend/app/database.py:69-79`

Each call to `owned_card`, `owned_column`, and `get_board` calls `board_for_user`, which issues `INSERT OR IGNORE` for the user row and the board row. A move request triggers this 3-4 times per HTTP call.

**Fix:** Accept `board_id` as an optional parameter in `owned_card`/`owned_column`, or resolve the board once at the top of each endpoint and thread it through.

---

### 10. `BoardOperation` fields not validated per operation type
**File:** `backend/app/ai.py:16-24`

All fields except `type` are `Optional`. An AI response like `{"type": "rename_column"}` (missing `column_id` and `title`) passes Pydantic validation and only fails later inside `apply_board_operations`, mixing parsing and application concerns.

**Fix:** Use a discriminated union — one Pydantic model per operation type with its required fields marked non-optional. `AIResponse.operations` becomes `list[Annotated[RenameColumn | CreateCard | ..., Field(discriminator="type")]]`.

---

### 11. AI prompt encodes history as JSON, not as message turns
**File:** `backend/app/ai.py:43-55`

The conversation history is packed into a JSON field inside a single user message rather than being sent as alternating `role`/`content` pairs in the `messages` array. LLMs are trained on proper turn-based conversation; embedding history as a JSON blob degrades instruction-following quality.

**Fix:** Build `messages` as a list of `{"role": ..., "content": ...}` dicts — system instruction first, then the alternating history, then a final user message with the current board state appended.

---

### 12. `onUnauthorized` callback recreated each render causes spurious board re-fetch
**Files:** `frontend/src/components/AuthGate.tsx:54`, `KanbanBoard.tsx:47`

`AuthGate` passes `() => setIsAuthenticated(false)` inline. This creates a new function reference on every render. `KanbanBoard` lists `onUnauthorized` in its `useEffect` dependency array, so the board is re-fetched whenever `AuthGate` re-renders.

**Fix:** Wrap in `useCallback` in `AuthGate`:
```tsx
const handleUnauthorized = useCallback(() => setIsAuthenticated(false), []);
```

---

### 13. `KanbanColumn` key forces full child remount on rename
**File:** `frontend/src/components/KanbanBoard.tsx:171`

```tsx
key={`${column.id}-${column.title}`}
```

This remounts the entire column (including all cards) on every title change — done to reset the column's local `title` state. The column's input already has its own key (`frontend/src/components/KanbanColumn.tsx:47`) that resets just the input on prop change.

**Fix:** Remove the `column.title` part from the column key; the input-level key is sufficient.

---

### 14. `initialData` and `createId` are dead code in production
**File:** `frontend/src/lib/kanban.ts:18, 164`

`initialData` was used by the pre-backend demo. `createId` is not called anywhere in the current codebase. Both are exported and bundled into the static output.

**Fix:** Delete both exports. Remove any test references to `initialData`.

---

### 15. Schema initialisation runs on every DB connection
**File:** `backend/app/database.py:34`

`initialize(connection)` (which runs the full `CREATE TABLE IF NOT EXISTS` DDL block) is called inside `connect()`, so it runs on every request. This is safe but wasteful.

**Fix:** Run `initialize` once at application startup using a FastAPI `lifespan` handler, then remove the call from `connect()`.

---

## Test Coverage Gaps

### 16. Drag-and-drop has no browser-level test
**File:** `frontend/tests/kanban.spec.ts:27-47, 80-98`

Both move tests bypass the UI entirely and call the API directly via `page.request.post`. The dnd-kit integration — sensors, overlay, collision detection, drop zones — is untested in the browser.

**Action:** Add a Playwright test that performs an actual drag gesture using `page.dragAndDrop` or the pointer-event sequence and asserts the card appears in the target column in the DOM.

---

### 17. No test for chat history limit
**File:** `backend/tests/test_main.py`

The 20-message bound in `recent_chat_messages` is not tested. Nor is the history hydration on the chat endpoint (that the `history` field in the prompt is bounded).

**Action:** Add a test that posts 25 chat exchanges and asserts the prompt sent to OpenRouter contains at most 20 history entries.

---

### 18. No test for 422 validation paths
**File:** `backend/tests/test_main.py`

Not tested: empty card title on create, empty card title on edit, empty column title on rename, negative move position, empty chat message.

**Action:** Add one parametrised test covering each 422 case.

---

### 19. No unit tests for `ChatSidebar`, `AuthGate`, or `KanbanCard`
**File:** `frontend/src/components/`

The three most interactive components — the ones containing the bugs described above — have zero unit test coverage.

**Action:** Add Vitest + Testing Library tests for at minimum: `KanbanCard` (edit opens with current values, cancel resets, save calls onEdit), `ChatSidebar` (optimistic message, error removes message), `AuthGate` (shows login, success shows board, logout clears state).

---

### 20. No e2e test for failed login or session expiry
**File:** `frontend/tests/kanban.spec.ts`

Wrong credentials and the `onUnauthorized` re-auth flow have no browser coverage.

**Action:** Add tests for: invalid credentials show error message; accessing board after session expires redirects to login.

---

## Summary Table

| # | Severity | Area | One-line description |
|---|----------|------|----------------------|
| 1 | Bug | Frontend | Card edit form shows stale values after board update |
| 2 | Bug | Frontend | Cancel button leaves dirty edit state |
| 3 | Bug | Frontend | Orphaned optimistic message on chat error |
| 4 | Bug | Backend | `rename_column` passes no `user_id` to `get_board` |
| 5 | Bug | Backend | Two DB connections around AI call create race window |
| 6 | Security | Backend | `SESSION_SECRET` falls back to a known string silently |
| 7 | Security | Backend | No chat message length limit |
| 8 | Quality | Backend | Duplicate move-card logic in two places |
| 9 | Quality | Backend | `board_for_user` called 3-4× per request |
| 10 | Quality | Backend | `BoardOperation` validated per-field, not per-type |
| 11 | Quality | Backend | AI history sent as JSON blob, not message turns |
| 12 | Quality | Frontend | Inline `onUnauthorized` causes spurious board re-fetch |
| 13 | Quality | Frontend | Column key on title remounts all card children |
| 14 | Quality | Frontend | `initialData` and `createId` are dead code |
| 15 | Quality | Backend | DB schema init runs on every connection |
| 16 | Tests | Frontend | Drag-and-drop not tested in browser |
| 17 | Tests | Backend | Chat history 20-message limit untested |
| 18 | Tests | Backend | No 422 validation path tests |
| 19 | Tests | Frontend | `ChatSidebar`, `AuthGate`, `KanbanCard` have no unit tests |
| 20 | Tests | Frontend | No e2e test for failed login or session expiry |
