# Database schema

## Approach

The application uses one local SQLite database file, created automatically when it
does not exist. SQLite stores the normalized relational data; API requests and
responses use JSON. A separate JSON file is not used as a database.

Each user account can own any number of boards. Board ownership is the security
boundary: every board, column, card, and chat-message read or write is scoped to
`board_id`, and every board-scoped request first checks that the signed-in user
owns that `board_id` before touching any row under it (see `owned_board` in
`backend/app/database.py`).

## Tables

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL DEFAULT ''
);

CREATE TABLE boards (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'Board',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX boards_by_user ON boards(user_id);

CREATE TABLE columns (
  id TEXT PRIMARY KEY,
  board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 4),
  UNIQUE (board_id, position)
);

CREATE TABLE cards (
  id TEXT PRIMARY KEY,
  column_id TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  position INTEGER NOT NULL CHECK (position >= 0),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (column_id, position)
);

CREATE INDEX cards_by_column_position ON cards(column_id, position);

CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX chat_messages_by_board ON chat_messages(board_id, id);
```

`boards.user_id` has no uniqueness constraint — a user can own many boards. The
application creates exactly five columns per board at positions 0–4 and exposes
no column create/delete endpoints, so columns stay fixed in count while their
titles can change. Column and card ids are namespaced with their board's id
(e.g. `<board_id>-col-backlog`) so ids stay globally unique across every user's
boards, since `columns.id` and `cards.id` are global primary keys, not
board-scoped.

`cards.position` defines order within a column. Board ownership is resolved by
following `cards.column_id` to `columns.board_id` to `boards.user_id`.

## Migrating from the single-board schema

Earlier versions of this app had exactly one board per user
(`boards.user_id UNIQUE`) and no `users.password_hash` / `boards.title` columns.
`database.initialize()` detects and upgrades an existing database on every
connection, in this order:

1. Add `users.password_hash` and `boards.title` if missing (`ALTER TABLE ADD COLUMN`,
   safe to run repeatedly).
2. If `boards.user_id` is still `UNIQUE`, rebuild the `boards` table without that
   constraint before any dependent table (`columns`, `chat_messages`) is created.
   This has to happen with both `PRAGMA foreign_keys` and `PRAGMA legacy_alter_table`
   turned off/on around the rename — SQLite otherwise silently rewrites the
   dependent tables' `REFERENCES boards(id)` clauses to point at the intermediate
   `boards_old` name, which then no longer exists once the rename finishes,
   breaking every future insert into `columns`/`cards`/`chat_messages`.

Because migration is columns-only (no data movement) except for the one
`boards` table rebuild (which copies rows by id, giving every pre-existing board
the title `'Board'`), all existing users, boards, columns, cards, and chat
history survive the upgrade untouched. Old accounts created before password
hashing existed have an empty `password_hash` and can no longer log in with
their old credentials (`verify_password` always rejects an empty hash) — they
need to register a new account.

## First-run initialization

On successful registration, the backend creates:

1. the new user's row (with a bcrypt password hash);
2. one starter board for that user, titled "My board";
3. five columns using the original demo's titles and positions;
4. the original demo cards, seeded only on this first board.

Boards created afterwards (via `POST /api/boards`) get the same five fixed
columns, but start with no cards.

## API representation

A board (`GET /api/boards/{board_id}`) returns:

```json
{
  "id": "board-1a2b3c4d",
  "title": "My board",
  "columns": [
    { "id": "board-1a2b3c4d-col-backlog", "title": "Backlog", "cardIds": ["board-1a2b3c4d-card-1"] },
    { "id": "board-1a2b3c4d-col-discovery", "title": "Discovery", "cardIds": [] }
  ],
  "cards": {
    "board-1a2b3c4d-card-1": {
      "id": "board-1a2b3c4d-card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics."
    }
  }
}
```

`GET /api/boards` returns the signed-in user's boards as a lightweight list:
`{"boards": [{"id": "...", "title": "..."}, ...]}`. The backend constructs all of
this JSON from SQLite rows, ordered by column and card position; JSON is the API
contract, not a duplicate data store.

## Mutation rules

- Every board-scoped request first verifies the session's user owns `board_id`.
- Create board appends a new board with five empty fixed columns.
- Rename board updates only the board's title; delete board removes it (and,
  via `ON DELETE CASCADE`, its columns/cards/chat history).
- Rename column updates only a column title.
- Create card appends a card at the target column's next position.
- Edit card updates card title and/or details only after ownership verification.
- Delete card removes the card, then compacts later positions in that column.
- Move/reorder card removes the card from its old position, compacts the old
  column, makes room in the target column, and writes the new position.

Each mutation runs in one SQLite transaction and returns the complete canonical
board JSON. A failed validation, missing board/column/card, or unauthorized
request rolls the entire transaction back.

## Chat history

Chat messages are stored in the user- and board-linked `chat_messages` table, so
history is private per board as well as per user. The chat endpoint saves the
user message and assistant response in one transaction with any board
operations. The history endpoint returns the recent messages used to hydrate
the sidebar; prompts are bounded to the latest 20 messages.
