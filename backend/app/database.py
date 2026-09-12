import os
import secrets
import sqlite3
from pathlib import Path

import bcrypt
from fastapi import HTTPException


SEED_COLUMNS = [
    ("col-backlog", "Backlog"),
    ("col-discovery", "Discovery"),
    ("col-progress", "In Progress"),
    ("col-review", "Review"),
    ("col-done", "Done"),
]

SEED_CARDS = [
    ("card-1", "col-backlog", "Align roadmap themes", "Draft quarterly themes with impact statements and metrics."),
    ("card-2", "col-backlog", "Gather customer signals", "Review support tags, sales notes, and churn feedback."),
    ("card-3", "col-discovery", "Prototype analytics view", "Sketch initial dashboard layout and key drill-downs."),
    ("card-4", "col-progress", "Refine status language", "Standardize column labels and tone across the board."),
    ("card-5", "col-progress", "Design card layout", "Add hierarchy and spacing for scanning dense lists."),
    ("card-6", "col-review", "QA micro-interactions", "Verify hover, focus, and loading states."),
    ("card-7", "col-done", "Ship marketing page", "Final copy approved and asset pack delivered."),
    ("card-8", "col-done", "Close onboarding sprint", "Document release notes and share internally."),
]


def connect() -> sqlite3.Connection:
    database_path = Path(os.environ.get("DATABASE_PATH", "data/pm.db"))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize(connection)
    return connection


def write_connect() -> sqlite3.Connection:
    """Open a write transaction that locks the database before any read.

    SQLite only applies the UNIQUE (column_id, position) constraint safely when
    concurrent mutations are serialized; BEGIN IMMEDIATE acquires the writer lock
    up front instead of racing read-then-write snapshots."""
    connection = connect()
    connection.execute("BEGIN IMMEDIATE")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    # `boards` must reach its final schema before columns/cards/chat_messages are created:
    # SQLite silently rewrites their FK clauses to point at a renamed table, so migrating
    # `boards` afterwards (see _drop_boards_one_per_user_constraint) would leave those FKs
    # dangling on a dropped `boards_old`.
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY,
          username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS boards (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL DEFAULT 'Board',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    _ensure_column(connection, "users", "password_hash", "password_hash TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "boards", "title", "title TEXT NOT NULL DEFAULT 'Board'")
    _drop_boards_one_per_user_constraint(connection)

    connection.executescript("""
        CREATE INDEX IF NOT EXISTS boards_by_user ON boards(user_id);
        CREATE TABLE IF NOT EXISTS columns (
          id TEXT PRIMARY KEY, board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
          title TEXT NOT NULL, position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 4),
          UNIQUE (board_id, position)
        );
        CREATE TABLE IF NOT EXISTS cards (
          id TEXT PRIMARY KEY, column_id TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
          title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL CHECK (position >= 0),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (column_id, position)
        );
        CREATE INDEX IF NOT EXISTS cards_by_column_position ON cards(column_id, position);
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS chat_messages_by_board ON chat_messages(board_id, id);
    """)


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _drop_boards_one_per_user_constraint(connection: sqlite3.Connection) -> None:
    """Older schema had `boards.user_id UNIQUE` (one board per user); rebuild without it.

    On a DB that already has `columns`/`chat_messages` referencing `boards(id)`, a plain
    rename makes SQLite silently rewrite those FK clauses to point at the doomed
    `boards_old` (RENAME TABLE's default behavior, meant to keep FKs valid when a table is
    renamed for good — and it applies whenever `foreign_keys` is on, regardless of
    `legacy_alter_table`). Both pragmas have to be flipped together to suppress it, so the
    dependent tables keep referencing `boards` — which still exists, just re-created, once
    this finishes."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'boards'"
    ).fetchone()
    if row and row["sql"] and "user_id TEXT NOT NULL UNIQUE" in row["sql"]:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA legacy_alter_table = ON")
        try:
            connection.executescript("""
                ALTER TABLE boards RENAME TO boards_old;
                CREATE TABLE boards (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  title TEXT NOT NULL DEFAULT 'Board',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO boards (id, user_id, title, created_at, updated_at)
                  SELECT id, user_id, COALESCE(NULLIF(title, ''), 'Board'), created_at, updated_at FROM boards_old;
                DROP TABLE boards_old;
                CREATE INDEX IF NOT EXISTS boards_by_user ON boards(user_id);
            """)
        finally:
            connection.execute("PRAGMA legacy_alter_table = OFF")
            connection.execute("PRAGMA foreign_keys = ON")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_user_by_username(connection: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(connection: sqlite3.Connection, username: str, password: str) -> str:
    user_id = f"user-{secrets.token_hex(8)}"
    connection.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
        (user_id, username, hash_password(password)),
    )
    return user_id


def insert_board(connection: sqlite3.Connection, user_id: str, title: str, seed: bool = False) -> str:
    """Create a board with five fixed columns. `id` is a global PRIMARY KEY across all
    boards, so every column/card id is namespaced under this board's id — never reuse
    the bare SEED_COLUMNS/SEED_CARDS ids directly, or two users' boards would collide."""
    board_id = f"board-{secrets.token_hex(8)}"
    connection.execute(
        "INSERT INTO boards (id, user_id, title) VALUES (?, ?, ?)", (board_id, user_id, title)
    )
    column_ids = {}
    for position, (seed_column_id, column_title) in enumerate(SEED_COLUMNS):
        column_id = f"{board_id}-{seed_column_id}"
        column_ids[seed_column_id] = column_id
        connection.execute(
            "INSERT INTO columns (id, board_id, title, position) VALUES (?, ?, ?, ?)",
            (column_id, board_id, column_title, position),
        )
    if seed:
        for seed_card_id, seed_column_id, card_title, details in SEED_CARDS:
            column_id = column_ids[seed_column_id]
            position = connection.execute(
                "SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)
            ).fetchone()[0]
            card_id = f"{board_id}-{seed_card_id}"
            connection.execute(
                "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
                (card_id, column_id, card_title, details, position),
            )
    return board_id


def boards_for_user(connection: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = connection.execute(
        "SELECT id, title FROM boards WHERE user_id = ? ORDER BY created_at, id", (user_id,)
    ).fetchall()
    return [{"id": row["id"], "title": row["title"]} for row in rows]


def owned_board(connection: sqlite3.Connection, board_id: str, user_id: str) -> sqlite3.Row:
    board = connection.execute(
        "SELECT * FROM boards WHERE id = ? AND user_id = ?", (board_id, user_id)
    ).fetchone()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


def update_board_title(connection: sqlite3.Connection, board_id: str, title: str) -> None:
    connection.execute(
        "UPDATE boards SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, board_id)
    )


def remove_board(connection: sqlite3.Connection, board_id: str) -> None:
    connection.execute("DELETE FROM boards WHERE id = ?", (board_id,))


def get_board(connection: sqlite3.Connection, board_id: str) -> dict:
    columns = connection.execute(
        "SELECT * FROM columns WHERE board_id = ? ORDER BY position", (board_id,)
    ).fetchall()
    cards = connection.execute(
        "SELECT cards.* FROM cards JOIN columns ON cards.column_id = columns.id "
        "WHERE columns.board_id = ? ORDER BY cards.position",
        (board_id,),
    ).fetchall()
    cards_by_column: dict[str, list[str]] = {column["id"]: [] for column in columns}
    card_data = {}
    for card in cards:
        cards_by_column[card["column_id"]].append(card["id"])
        card_data[card["id"]] = {"id": card["id"], "title": card["title"], "details": card["details"]}
    return {
        "columns": [
            {"id": col["id"], "title": col["title"], "cardIds": cards_by_column[col["id"]]}
            for col in columns
        ],
        "cards": card_data,
    }


def owned_column(connection: sqlite3.Connection, column_id: str, board_id: str) -> sqlite3.Row:
    column = connection.execute(
        "SELECT * FROM columns WHERE id = ? AND board_id = ?", (column_id, board_id)
    ).fetchone()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    return column


def owned_card(connection: sqlite3.Connection, card_id: str, board_id: str) -> sqlite3.Row:
    card = connection.execute(
        "SELECT cards.* FROM cards JOIN columns ON cards.column_id = columns.id "
        "WHERE cards.id = ? AND columns.board_id = ?",
        (card_id, board_id),
    ).fetchone()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def rewrite_positions(connection: sqlite3.Connection, column_id: str, card_ids: list[str]) -> None:
    # Two-phase update avoids UNIQUE (column_id, position) conflicts during reordering.
    current_max = connection.execute(
        "SELECT COALESCE(MAX(position), 0) FROM cards WHERE column_id = ?", (column_id,)
    ).fetchone()[0]
    temporary_base = current_max + len(card_ids) + 1
    for index, card_id in enumerate(card_ids):
        connection.execute("UPDATE cards SET position = ? WHERE id = ?", (temporary_base + index, card_id))
    for index, card_id in enumerate(card_ids):
        connection.execute(
            "UPDATE cards SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (index, card_id),
        )


def do_move_card(
    connection: sqlite3.Connection, card_id: str, column_id: str, position: int, board_id: str
) -> None:
    """Move card_id to column_id at position. Validates ownership, updates positions atomically."""
    card = owned_card(connection, card_id, board_id)
    owned_column(connection, column_id, board_id)
    source_ids = [
        row["id"]
        for row in connection.execute(
            "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],)
        )
    ]
    if card["column_id"] == column_id:
        source_ids.remove(card_id)
        source_ids.insert(min(position, len(source_ids)), card_id)
        rewrite_positions(connection, column_id, source_ids)
    else:
        target_ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (column_id,)
            )
        ]
        source_ids.remove(card_id)
        target_ids.insert(min(position, len(target_ids)), card_id)
        # Park the card outside the valid range so source compaction doesn't conflict.
        connection.execute(
            "UPDATE cards SET position = 2000000, column_id = ? WHERE id = ?", (column_id, card_id)
        )
        rewrite_positions(connection, card["column_id"], source_ids)
        rewrite_positions(connection, column_id, target_ids)


def save_chat_message(
    connection: sqlite3.Connection, user_id: str, board_id: str, role: str, content: str
) -> None:
    connection.execute(
        "INSERT INTO chat_messages (user_id, board_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, board_id, role, content),
    )


def recent_chat_messages(
    connection: sqlite3.Connection, user_id: str, board_id: str, limit: int = 20
) -> list[dict[str, str]]:
    rows = connection.execute(
        "SELECT role, content FROM chat_messages "
        "WHERE user_id = ? AND board_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, board_id, limit),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def apply_board_operations(connection: sqlite3.Connection, board_id: str, operations: list) -> None:
    for op in operations:
        if op.type == "rename_column":
            title = op.title.strip()
            if not title:
                raise ValueError("rename_column: title cannot be empty")
            owned_column(connection, op.column_id, board_id)
            connection.execute(
                "UPDATE columns SET title = ? WHERE id = ?", (title, op.column_id)
            )
        elif op.type == "create_card":
            title = op.title.strip()
            if not title:
                raise ValueError("create_card: title cannot be empty")
            owned_column(connection, op.column_id, board_id)
            position = connection.execute(
                "SELECT COUNT(*) FROM cards WHERE column_id = ?", (op.column_id,)
            ).fetchone()[0]
            card_id = f"card-ai-{os.urandom(8).hex()}"
            connection.execute(
                "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
                (card_id, op.column_id, title, (op.details or "").strip(), position),
            )
        elif op.type == "edit_card":
            card = owned_card(connection, op.card_id, board_id)
            title = card["title"] if op.title is None else op.title.strip()
            if not title:
                raise ValueError("edit_card: title cannot be empty")
            details = card["details"] if op.details is None else op.details.strip()
            connection.execute(
                "UPDATE cards SET title = ?, details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, details, op.card_id),
            )
        elif op.type == "delete_card":
            card = owned_card(connection, op.card_id, board_id)
            connection.execute("DELETE FROM cards WHERE id = ?", (op.card_id,))
            remaining = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],)
                )
            ]
            rewrite_positions(connection, card["column_id"], remaining)
        elif op.type == "move_card":
            do_move_card(connection, op.card_id, op.column_id, op.position, board_id)
