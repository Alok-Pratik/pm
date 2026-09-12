import sqlite3

import pytest

from app import database


@pytest.fixture
def db_path(tmp_path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "pm.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    return path


def _create_legacy_schema(path) -> None:
    """Recreates the pre-multi-board schema: one board per user (UNIQUE constraint),
    no password_hash/title columns, columns/cards/chat_messages already populated."""
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE);
        CREATE TABLE boards (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE columns (
          id TEXT PRIMARY KEY, board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
          title TEXT NOT NULL, position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 4),
          UNIQUE (board_id, position)
        );
        CREATE TABLE cards (
          id TEXT PRIMARY KEY, column_id TEXT NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
          title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL CHECK (position >= 0),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (column_id, position)
        );
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            board_id TEXT NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    connection.execute("INSERT INTO users (id, username) VALUES ('user', 'user')")
    connection.execute("INSERT INTO boards (id, user_id) VALUES ('board-user', 'user')")
    connection.execute(
        "INSERT INTO columns (id, board_id, title, position) VALUES ('col-backlog', 'board-user', 'Backlog', 0)"
    )
    connection.execute(
        "INSERT INTO cards (id, column_id, title, details, position) VALUES ('card-1', 'col-backlog', 'Old card', '', 0)"
    )
    connection.execute(
        "INSERT INTO chat_messages (user_id, board_id, role, content) VALUES ('user', 'board-user', 'user', 'hi')"
    )
    connection.commit()
    connection.close()


def test_migrating_legacy_one_board_per_user_schema_preserves_data_and_allows_second_board(db_path) -> None:
    _create_legacy_schema(db_path)

    with database.connect() as connection:
        boards = database.boards_for_user(connection, "user")
        assert boards == [{"id": "board-user", "title": "Board"}]

        preserved = database.get_board(connection, "board-user")
        assert preserved == {
            "columns": [{"id": "col-backlog", "title": "Backlog", "cardIds": ["card-1"]}],
            "cards": {"card-1": {"id": "card-1", "title": "Old card", "details": ""}},
        }
        assert database.recent_chat_messages(connection, "user", "board-user") == [
            {"role": "user", "content": "hi"}
        ]

        second_board_id = database.insert_board(connection, "user", "Second board")
        connection.commit()

        all_boards = database.boards_for_user(connection, "user")
        assert {b["id"] for b in all_boards} == {"board-user", second_board_id}
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_is_idempotent_across_repeated_connects(db_path) -> None:
    _create_legacy_schema(db_path)

    with database.connect():
        pass
    with database.connect() as connection:
        assert database.boards_for_user(connection, "user") == [{"id": "board-user", "title": "Board"}]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_password_hash_round_trip() -> None:
    hashed = database.hash_password("correct horse battery staple")
    assert database.verify_password("correct horse battery staple", hashed)
    assert not database.verify_password("wrong password", hashed)


def test_verify_password_rejects_blank_hash() -> None:
    assert not database.verify_password("anything", "")


def test_insert_board_namespaces_column_and_card_ids_per_board(db_path) -> None:
    with database.connect() as connection:
        user_id = database.create_user(connection, "alice", "password123")
        board_a = database.insert_board(connection, user_id, "A", seed=True)
        board_b = database.insert_board(connection, user_id, "B", seed=True)
        connection.commit()

        columns_a = {c["id"] for c in database.get_board(connection, board_a)["columns"]}
        columns_b = {c["id"] for c in database.get_board(connection, board_b)["columns"]}
        assert columns_a.isdisjoint(columns_b)

        cards_a = set(database.get_board(connection, board_a)["cards"])
        cards_b = set(database.get_board(connection, board_b)["cards"])
        assert cards_a.isdisjoint(cards_b)
