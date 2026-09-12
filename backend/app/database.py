import os
import sqlite3
from pathlib import Path

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


def initialize(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS boards (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
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


def resolve_board(connection: sqlite3.Connection, user_id: str = "user") -> str:
    """Ensure user/board rows and seed data exist; return board_id."""
    connection.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, user_id))
    board_id = f"board-{user_id}"
    connection.execute("INSERT OR IGNORE INTO boards (id, user_id) VALUES (?, ?)", (board_id, user_id))
    if connection.execute("SELECT COUNT(*) FROM columns WHERE board_id = ?", (board_id,)).fetchone()[0] == 0:
        for position, (column_id, title) in enumerate(SEED_COLUMNS):
            connection.execute("INSERT INTO columns VALUES (?, ?, ?, ?)", (column_id, board_id, title, position))
        for card_id, column_id, title, details in SEED_CARDS:
            position = connection.execute("SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)).fetchone()[0]
            connection.execute(
                "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
                (card_id, column_id, title, details, position),
            )
    return board_id


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
            owned_column(connection, op.column_id, board_id)
            connection.execute(
                "UPDATE columns SET title = ? WHERE id = ?", (op.title.strip(), op.column_id)
            )
        elif op.type == "create_card":
            owned_column(connection, op.column_id, board_id)
            position = connection.execute(
                "SELECT COUNT(*) FROM cards WHERE column_id = ?", (op.column_id,)
            ).fetchone()[0]
            card_id = f"card-ai-{os.urandom(8).hex()}"
            connection.execute(
                "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
                (card_id, op.column_id, op.title.strip(), (op.details or "").strip(), position),
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
