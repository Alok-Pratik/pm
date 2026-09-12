# Database schema proposal

## Approach

The application will use one local SQLite database file, created automatically
when it does not exist. SQLite stores the normalized relational data; API
requests and responses use JSON. A separate JSON file is not used as a
database.

This keeps board reads and card moves simple while retaining the ownership model
needed for future users.

## Tables

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE
);

CREATE TABLE boards (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

`boards.user_id` is unique, enforcing one board per user. The application
creates exactly five columns at positions 0–4 and exposes no column
create/delete endpoints, so columns stay fixed while their titles can change.

`cards.position` defines order within a column. Board ownership is resolved by
following `cards.column_id` to `columns.board_id` to `boards.user_id`.

## First-run initialization

When the database file is absent, the backend creates these tables in one
transaction. On the first successful login for `user`, it creates:

1. the `user` row;
2. that user’s sole board;
3. five columns using the existing demo’s titles and positions;
4. the existing demo cards and their current order.

The initialization checks whether the user already owns a board, so it is safe
to run on every request without duplicating data.

## API representation

The board endpoint returns the shape already used by the frontend:

```json
{
  "columns": [
    { "id": "col-backlog", "title": "Backlog", "cardIds": ["card-1"] },
    { "id": "col-discovery", "title": "Discovery", "cardIds": [] }
  ],
  "cards": {
    "card-1": {
      "id": "card-1",
      "title": "Align roadmap themes",
      "details": "Draft quarterly themes with impact statements and metrics."
    }
  }
}
```

The backend constructs this JSON from SQLite rows, ordered by column and card
position. JSON is the API contract, not a duplicate data store.

## Mutation rules

- Every board request first verifies the session’s user owns the board.
- Rename updates only a column title.
- Create appends a card at the target column’s next position.
- Edit updates card title and/or details only after ownership verification.
- Delete removes the card, then compacts later positions in that column.
- Move/reorder removes the card from its old position, compacts the old column,
  makes room in the target column, and writes the new position.

Each mutation runs in one SQLite transaction and returns the complete canonical
board JSON. A failed validation, missing card/column, or unauthorized request
rolls the entire transaction back.

## Chat history

Chat messages are stored in the user- and board-linked `chat_messages` table.
The chat endpoint saves the user message and assistant response in one
transaction with any board operations. The history endpoint returns the recent
messages used to hydrate the sidebar; prompts are bounded to the latest 20
messages.
