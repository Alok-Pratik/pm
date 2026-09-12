import json

from fastapi.testclient import TestClient
import pytest

from app.main import app, _MAX_CHAT_MESSAGE_LEN


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "pm.db"))


def client() -> TestClient:
    return TestClient(app)


def register(browser: TestClient, username: str = "alice", password: str = "password123") -> dict:
    response = browser.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def sign_in_new_user(username: str = "alice", password: str = "password123") -> TestClient:
    browser = client()
    register(browser, username, password)
    return browser


def first_board_id(browser: TestClient) -> str:
    return browser.get("/api/boards").json()["boards"][0]["id"]


def test_health() -> None:
    assert client().get("/health").json() == {"status": "ok"}


def test_boards_require_authentication() -> None:
    assert client().get("/api/boards").status_code == 401


# --- Registration ---


def test_register_creates_account_and_signs_in_with_starter_board() -> None:
    browser = client()
    data = register(browser)
    assert data == {"authenticated": True, "username": "alice"}
    assert browser.get("/api/auth/session").json() == {"authenticated": True, "username": "alice"}

    boards = browser.get("/api/boards").json()["boards"]
    assert len(boards) == 1
    board = browser.get(f"/api/boards/{boards[0]['id']}").json()
    assert len(board["columns"]) == 5
    assert len(board["cards"]) == 8


def test_register_rejects_duplicate_username() -> None:
    browser = client()
    register(browser, "bob")
    response = client().post("/api/auth/register", json={"username": "bob", "password": "password123"})
    assert response.status_code == 409


@pytest.mark.parametrize("username", ["", "ab", "a" * 33, "has space", "bad!name"])
def test_register_rejects_invalid_username(username: str) -> None:
    response = client().post("/api/auth/register", json={"username": username, "password": "password123"})
    assert response.status_code == 422


@pytest.mark.parametrize("password", ["", "short", "x" * 129])
def test_register_rejects_invalid_password(password: str) -> None:
    response = client().post("/api/auth/register", json={"username": "carol", "password": password})
    assert response.status_code == 422


def test_password_is_never_returned() -> None:
    browser = client()
    data = register(browser, "dave", "supersecret1")
    assert "password" not in data
    assert "password_hash" not in data


# --- Login / session ---


def test_login_and_logout() -> None:
    browser = client()
    register(browser, "erin", "password123")
    browser.post("/api/auth/logout")
    assert browser.get("/api/auth/session").json() == {"authenticated": False}

    response = browser.post("/api/auth/login", json={"username": "erin", "password": "password123"})
    assert response.status_code == 200
    assert browser.get("/api/auth/session").json() == {"authenticated": True, "username": "erin"}

    assert browser.post("/api/auth/logout").json() == {"authenticated": False}
    assert browser.get("/api/boards").status_code == 401


def test_invalid_credentials_are_rejected() -> None:
    browser = client()
    register(browser, "frank", "password123")
    response = client().post("/api/auth/login", json={"username": "frank", "password": "wrong"})
    assert response.status_code == 401


def test_login_rejects_unknown_username() -> None:
    response = client().post("/api/auth/login", json={"username": "ghost", "password": "password123"})
    assert response.status_code == 401


# --- Multi-board ---


def test_user_can_create_list_rename_and_delete_boards() -> None:
    browser = sign_in_new_user("gina")
    starter_board_id = first_board_id(browser)

    created = browser.post("/api/boards", json={"title": "Marketing"}).json()
    assert created["title"] == "Marketing"
    assert len(created["columns"]) == 5
    assert created["cards"] == {}

    boards = browser.get("/api/boards").json()["boards"]
    assert {b["id"] for b in boards} == {starter_board_id, created["id"]}

    renamed = browser.patch(f"/api/boards/{created['id']}", json={"title": "Growth"}).json()
    assert renamed["title"] == "Growth"

    deleted = browser.delete(f"/api/boards/{created['id']}").json()
    assert {b["id"] for b in deleted["boards"]} == {starter_board_id}


def test_create_board_defaults_title_when_blank() -> None:
    browser = sign_in_new_user("henry")
    created = browser.post("/api/boards", json={"title": "   "}).json()
    assert created["title"] == "Untitled board"


def test_rename_board_rejects_blank_title() -> None:
    browser = sign_in_new_user("iris")
    board_id = first_board_id(browser)
    assert browser.patch(f"/api/boards/{board_id}", json={"title": " "}).status_code == 422


def test_unknown_board_returns_404() -> None:
    browser = sign_in_new_user("jack")
    assert browser.get("/api/boards/missing-board").status_code == 404
    assert browser.patch("/api/boards/missing-board", json={"title": "x"}).status_code == 404
    assert browser.delete("/api/boards/missing-board").status_code == 404


# --- Cross-user isolation ---


def test_user_cannot_read_another_users_board() -> None:
    owner = sign_in_new_user("kim")
    other = sign_in_new_user("liam")
    owner_board_id = first_board_id(owner)

    assert other.get(f"/api/boards/{owner_board_id}").status_code == 404
    assert other.patch(f"/api/boards/{owner_board_id}", json={"title": "hijacked"}).status_code == 404
    assert other.delete(f"/api/boards/{owner_board_id}").status_code == 404


def test_user_cannot_mutate_cards_or_columns_on_another_users_board() -> None:
    owner = sign_in_new_user("mona")
    other = sign_in_new_user("nate")
    owner_board_id = first_board_id(owner)
    owner_board = owner.get(f"/api/boards/{owner_board_id}").json()
    owner_column_id = owner_board["columns"][0]["id"]
    owner_card_id = owner_board["columns"][0]["cardIds"][0]

    assert other.put(
        f"/api/boards/{owner_board_id}/columns/{owner_column_id}", json={"title": "Hacked"}
    ).status_code == 404
    assert other.post(
        f"/api/boards/{owner_board_id}/cards", json={"column_id": owner_column_id, "title": "Intruder"}
    ).status_code == 404
    assert other.patch(
        f"/api/boards/{owner_board_id}/cards/{owner_card_id}", json={"title": "Hacked"}
    ).status_code == 404
    assert other.delete(f"/api/boards/{owner_board_id}/cards/{owner_card_id}").status_code == 404
    assert other.post(
        f"/api/boards/{owner_board_id}/cards/{owner_card_id}/move",
        json={"column_id": owner_column_id, "position": 0},
    ).status_code == 404

    unchanged = owner.get(f"/api/boards/{owner_board_id}").json()
    assert unchanged == owner_board


def test_user_cannot_read_another_users_chat_history() -> None:
    owner = sign_in_new_user("olga")
    other = sign_in_new_user("paul")
    owner_board_id = first_board_id(owner)

    assert other.get(f"/api/boards/{owner_board_id}/chat/history").status_code == 404
    assert other.post(f"/api/boards/{owner_board_id}/chat", json={"message": "hi"}).status_code == 404


# --- Board contents (per-board) ---


def test_board_mutations_persist() -> None:
    browser = sign_in_new_user("quinn")
    board_id = first_board_id(browser)
    board = browser.get(f"/api/boards/{board_id}").json()
    assert len(board["columns"]) == 5
    column_id = board["columns"][0]["id"]

    board = browser.put(f"/api/boards/{board_id}/columns/{column_id}", json={"title": "Ideas"}).json()
    assert board["columns"][0]["title"] == "Ideas"

    board = browser.post(
        f"/api/boards/{board_id}/cards",
        json={"column_id": column_id, "title": "Persistent card", "details": "Saved"},
    ).json()
    card_id = next(key for key, value in board["cards"].items() if value["title"] == "Persistent card")

    review_column_id = board["columns"][3]["id"]
    board = browser.post(
        f"/api/boards/{board_id}/cards/{card_id}/move",
        json={"column_id": review_column_id, "position": 0},
    ).json()
    assert board["columns"][3]["cardIds"][0] == card_id

    board = browser.patch(f"/api/boards/{board_id}/cards/{card_id}", json={"title": "Updated card"}).json()
    assert board["cards"][card_id]["title"] == "Updated card"

    board = browser.delete(f"/api/boards/{board_id}/cards/{card_id}").json()
    assert card_id not in board["cards"]


def test_moving_a_card_within_a_column_reorders_it() -> None:
    browser = sign_in_new_user("ray")
    board_id = first_board_id(browser)
    board = browser.get(f"/api/boards/{board_id}").json()
    column_id = board["columns"][0]["id"]
    first_card, second_card = board["columns"][0]["cardIds"][:2]

    board = browser.post(
        f"/api/boards/{board_id}/cards/{first_card}/move",
        json={"column_id": column_id, "position": 1},
    ).json()
    assert board["columns"][0]["cardIds"][:2] == [second_card, first_card]


def test_repeated_cross_column_moves_preserve_order() -> None:
    browser = sign_in_new_user("sara")
    board_id = first_board_id(browser)
    board = browser.get(f"/api/boards/{board_id}").json()
    backlog_id, _, _, review_id, _ = [c["id"] for c in board["columns"]]
    card_1 = board["columns"][0]["cardIds"][0]
    card_6 = board["columns"][3]["cardIds"][0]

    browser.post(f"/api/boards/{board_id}/cards/{card_1}/move", json={"column_id": review_id, "position": 0})
    board = browser.post(
        f"/api/boards/{board_id}/cards/{card_6}/move", json={"column_id": backlog_id, "position": 0}
    ).json()
    assert board["columns"][0]["cardIds"][0] == card_6
    assert card_1 in board["columns"][3]["cardIds"]


def test_invalid_board_mutation_does_not_change_the_board() -> None:
    browser = sign_in_new_user("tara")
    board_id = first_board_id(browser)
    original = browser.get(f"/api/boards/{board_id}").json()
    card_1 = original["columns"][0]["cardIds"][0]

    response = browser.post(
        f"/api/boards/{board_id}/cards/{card_1}/move", json={"column_id": "missing", "position": 0}
    )
    assert response.status_code == 404
    assert browser.get(f"/api/boards/{board_id}").json() == original


@pytest.mark.parametrize("title", ["", "   "])
def test_create_card_rejects_blank_title(title: str) -> None:
    browser = sign_in_new_user("uma")
    board_id = first_board_id(browser)
    column_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["id"]
    assert browser.post(
        f"/api/boards/{board_id}/cards", json={"column_id": column_id, "title": title}
    ).status_code == 422


@pytest.mark.parametrize("title", ["", "   "])
def test_rename_column_rejects_blank_title(title: str) -> None:
    browser = sign_in_new_user("vince")
    board_id = first_board_id(browser)
    column_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["id"]
    assert browser.put(
        f"/api/boards/{board_id}/columns/{column_id}", json={"title": title}
    ).status_code == 422


def test_edit_card_rejects_blank_title() -> None:
    browser = sign_in_new_user("wendy")
    board_id = first_board_id(browser)
    card_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["cardIds"][0]
    assert browser.patch(f"/api/boards/{board_id}/cards/{card_id}", json={"title": ""}).status_code == 422


def test_move_card_rejects_negative_position() -> None:
    browser = sign_in_new_user("xena")
    board_id = first_board_id(browser)
    board = browser.get(f"/api/boards/{board_id}").json()
    column_id = board["columns"][0]["id"]
    card_id = board["columns"][0]["cardIds"][0]
    assert browser.post(
        f"/api/boards/{board_id}/cards/{card_id}/move", json={"column_id": column_id, "position": -1}
    ).status_code == 422


# --- Chat ---


class FakeOpenRouter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list = []

    async def complete_messages(self, messages: list) -> str:
        self.messages = messages
        return self.content


def test_chat_rejects_empty_message() -> None:
    browser = sign_in_new_user("yara")
    board_id = first_board_id(browser)
    assert browser.post(f"/api/boards/{board_id}/chat", json={"message": ""}).status_code == 422


def test_chat_rejects_message_over_limit() -> None:
    browser = sign_in_new_user("zane")
    board_id = first_board_id(browser)
    assert browser.post(
        f"/api/boards/{board_id}/chat", json={"message": "x" * (_MAX_CHAT_MESSAGE_LEN + 1)}
    ).status_code == 422


def test_chat_returns_no_op_response_and_board_context(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter(json.dumps({"version": 1, "message": "No changes needed.", "operations": []}))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = sign_in_new_user("amy")
    board_id = first_board_id(browser)
    column_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["id"]

    response = browser.post(f"/api/boards/{board_id}/chat", json={"message": "What is on the board?"})

    assert response.status_code == 200
    assert response.json()["message"] == "No changes needed."
    assert fake.messages[-1] == {"role": "user", "content": "What is on the board?"}
    assert column_id in fake.messages[0]["content"]

    history = browser.get(f"/api/boards/{board_id}/chat/history")
    assert history.status_code == 200
    assert history.json()["messages"][-1] == {"role": "assistant", "content": "No changes needed."}


def test_chat_applies_multiple_operations_atomically(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = sign_in_new_user("boaz")
    board_id = first_board_id(browser)
    column_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["id"]
    fake = FakeOpenRouter(json.dumps({
        "version": 1,
        "message": "I updated the board.",
        "operations": [
            {"type": "rename_column", "column_id": column_id, "title": "Ideas"},
            {"type": "create_card", "column_id": column_id, "title": "AI card", "details": "Created by AI"},
        ],
    }))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)

    response = browser.post(f"/api/boards/{board_id}/chat", json={"message": "Create an AI card."})

    assert response.status_code == 200
    board = response.json()["board"]
    assert board["columns"][0]["title"] == "Ideas"
    assert any(card["title"] == "AI card" for card in board["cards"].values())


def test_chat_rejects_malformed_model_output_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter("not JSON")
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = sign_in_new_user("cleo")
    board_id = first_board_id(browser)
    original = browser.get(f"/api/boards/{board_id}").json()

    response = browser.post(f"/api/boards/{board_id}/chat", json={"message": "Break the parser."})

    assert response.status_code == 502
    assert browser.get(f"/api/boards/{board_id}").json() == original


def test_chat_rejects_invalid_operation_without_partial_update(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = sign_in_new_user("dax")
    board_id = first_board_id(browser)
    column_id = browser.get(f"/api/boards/{board_id}").json()["columns"][0]["id"]
    fake = FakeOpenRouter(json.dumps({
        "version": 1,
        "message": "Attempted update.",
        "operations": [
            {"type": "rename_column", "column_id": column_id, "title": "Ideas"},
            {"type": "delete_card", "card_id": "missing-card"},
        ],
    }))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    original = browser.get(f"/api/boards/{board_id}").json()

    response = browser.post(f"/api/boards/{board_id}/chat", json={"message": "Make invalid changes."})

    assert response.status_code == 422
    assert browser.get(f"/api/boards/{board_id}").json() == original


def test_chat_history_is_bounded_to_20_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = sign_in_new_user("eli")
    board_id = first_board_id(browser)

    last_fake: FakeOpenRouter | None = None
    for i in range(25):
        content = json.dumps({"version": 1, "message": f"reply {i}", "operations": []})
        fake = FakeOpenRouter(content)
        monkeypatch.setattr("app.main.openrouter_service", lambda f=fake: f)
        browser.post(f"/api/boards/{board_id}/chat", json={"message": f"message {i}"})
        last_fake = fake

    history = browser.get(f"/api/boards/{board_id}/chat/history").json()
    assert len(history["messages"]) == 20

    assert last_fake is not None
    # system message + up to 20 history entries + current user message
    assert len(last_fake.messages) <= 22


def test_chat_history_is_isolated_per_board(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = sign_in_new_user("finn")
    board_a = first_board_id(browser)
    board_b = browser.post("/api/boards", json={"title": "Second"}).json()["id"]

    fake = FakeOpenRouter(json.dumps({"version": 1, "message": "ok on A", "operations": []}))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser.post(f"/api/boards/{board_a}/chat", json={"message": "hello A"})

    assert browser.get(f"/api/boards/{board_b}/chat/history").json()["messages"] == []
    assert len(browser.get(f"/api/boards/{board_a}/chat/history").json()["messages"]) == 2
