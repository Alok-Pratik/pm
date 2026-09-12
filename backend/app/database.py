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


def board_for_user(connection: sqlite3.Connection, user_id: str = "user") -> str:
    connection.execute("INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)", (user_id, user_id))
    board_id = f"board-{user_id}"
    connection.execute("INSERT OR IGNORE INTO boards (id, user_id) VALUES (?, ?)", (board_id, user_id))
    if connection.execute("SELECT COUNT(*) FROM columns WHERE board_id = ?", (board_id,)).fetchone()[0] == 0:
        for position, (column_id, title) in enumerate(SEED_COLUMNS):
            connection.execute("INSERT INTO columns VALUES (?, ?, ?, ?)", (column_id, board_id, title, position))
        for card_id, column_id, title, details in SEED_CARDS:
            position = connection.execute("SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)).fetchone()[0]
            connection.execute("INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)", (card_id, column_id, title, details, position))
    return board_id


def get_board(connection: sqlite3.Connection, user_id: str = "user") -> dict:
    board_id = board_for_user(connection, user_id)
    columns = connection.execute("SELECT * FROM columns WHERE board_id = ? ORDER BY position", (board_id,)).fetchall()
    cards = connection.execute("SELECT cards.* FROM cards JOIN columns ON cards.column_id = columns.id WHERE columns.board_id = ? ORDER BY cards.position", (board_id,)).fetchall()
    cards_by_column: dict[str, list[str]] = {column["id"]: [] for column in columns}
    card_data = {}
    for card in cards:
        cards_by_column[card["column_id"]].append(card["id"])
        card_data[card["id"]] = {"id": card["id"], "title": card["title"], "details": card["details"]}
    return {"columns": [{"id": column["id"], "title": column["title"], "cardIds": cards_by_column[column["id"]]} for column in columns], "cards": card_data}


def owned_column(connection: sqlite3.Connection, column_id: str, user_id: str) -> sqlite3.Row:
    board_id = board_for_user(connection, user_id)
    column = connection.execute("SELECT * FROM columns WHERE id = ? AND board_id = ?", (column_id, board_id)).fetchone()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    return column


def owned_card(connection: sqlite3.Connection, card_id: str, user_id: str) -> sqlite3.Row:
    board_id = board_for_user(connection, user_id)
    card = connection.execute("SELECT cards.* FROM cards JOIN columns ON cards.column_id = columns.id WHERE cards.id = ? AND columns.board_id = ?", (card_id, board_id)).fetchone()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


def rewrite_positions(connection: sqlite3.Connection, column_id: str, card_ids: list[str]) -> None:
    current_max = connection.execute(
        "SELECT COALESCE(MAX(position), 0) FROM cards WHERE column_id = ?",
        (column_id,),
    ).fetchone()[0]
    temporary_base = current_max + len(card_ids) + 1
    for index, card_id in enumerate(card_ids):
        connection.execute("UPDATE cards SET position = ? WHERE id = ?", (temporary_base + index, card_id))
    for index, card_id in enumerate(card_ids):
        connection.execute("UPDATE cards SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (index, card_id))


def save_chat_message(connection: sqlite3.Connection, user_id: str, role: str, content: str) -> None:
    board_id = board_for_user(connection, user_id)
    connection.execute(
        "INSERT INTO chat_messages (user_id, board_id, role, content) VALUES (?, ?, ?, ?)",
        (user_id, board_id, role, content),
    )


def recent_chat_messages(connection: sqlite3.Connection, user_id: str, limit: int = 20) -> list[dict[str, str]]:
    board_id = board_for_user(connection, user_id)
    rows = connection.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? AND board_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, board_id, limit),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def apply_board_operations(connection: sqlite3.Connection, user_id: str, operations: list[dict]) -> None:
    for operation in operations:
        operation_type = operation["type"]
        if operation_type == "rename_column":
            column_id = operation.get("column_id")
            title = (operation.get("title") or "").strip()
            if not column_id or not title:
                raise ValueError("rename_column requires column_id and title")
            owned_column(connection, column_id, user_id)
            connection.execute("UPDATE columns SET title = ? WHERE id = ?", (title, column_id))
        elif operation_type == "create_card":
            column_id = operation.get("column_id")
            title = (operation.get("title") or "").strip()
            if not column_id or not title:
                raise ValueError("create_card requires column_id and title")
            owned_column(connection, column_id, user_id)
            position = connection.execute("SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)).fetchone()[0]
            card_id = f"card-ai-{os.urandom(8).hex()}"
            connection.execute(
                "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
                (card_id, column_id, title, (operation.get("details") or "").strip(), position),
            )
        elif operation_type == "edit_card":
            card_id = operation.get("card_id")
            if not card_id:
                raise ValueError("edit_card requires card_id")
            card = owned_card(connection, card_id, user_id)
            title = card["title"] if operation.get("title") is None else operation["title"].strip()
            if not title:
                raise ValueError("edit_card requires a non-empty title")
            details = card["details"] if operation.get("details") is None else operation["details"].strip()
            connection.execute("UPDATE cards SET title = ?, details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, details, card_id))
        elif operation_type == "delete_card":
            card_id = operation.get("card_id")
            if not card_id:
                raise ValueError("delete_card requires card_id")
            card = owned_card(connection, card_id, user_id)
            connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
            remaining = [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],))]
            rewrite_positions(connection, card["column_id"], remaining)
        elif operation_type == "move_card":
            card_id = operation.get("card_id")
            column_id = operation.get("column_id")
            position = operation.get("position")
            if not card_id or not column_id or position is None:
                raise ValueError("move_card requires card_id, column_id, and position")
            card = owned_card(connection, card_id, user_id)
            owned_column(connection, column_id, user_id)
            source_ids = [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],))]
            target_ids = source_ids if card["column_id"] == column_id else [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (column_id,))]
            source_ids.remove(card_id)
            if card["column_id"] == column_id:
                target_ids = source_ids
            target_ids.insert(min(position, len(target_ids)), card_id)
            if card["column_id"] != column_id:
                connection.execute("UPDATE cards SET position = 2000000, column_id = ? WHERE id = ?", (column_id, card_id))
                rewrite_positions(connection, card["column_id"], source_ids)
            rewrite_positions(connection, column_id, target_ids)
