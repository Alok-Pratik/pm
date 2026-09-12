import json

from fastapi.testclient import TestClient
import pytest

from app.main import app, _MAX_CHAT_MESSAGE_LEN


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "pm.db"))


def client() -> TestClient:
    return TestClient(app)


def sign_in(browser: TestClient) -> None:
    assert browser.post("/api/auth/login", json={"username": "user", "password": "password"}).status_code == 200


def test_health() -> None:
    assert client().get("/health").json() == {"status": "ok"}


def test_board_requires_authentication() -> None:
    assert client().get("/api/board").status_code == 401


def test_login_and_logout() -> None:
    browser = client()
    assert browser.get("/api/auth/session").json() == {"authenticated": False}
    sign_in(browser)
    assert browser.get("/api/auth/session").json() == {"authenticated": True}
    assert browser.post("/api/auth/logout").json() == {"authenticated": False}
    assert browser.get("/api/board").status_code == 401


def test_invalid_credentials_are_rejected() -> None:
    response = client().post("/api/auth/login", json={"username": "user", "password": "wrong"})
    assert response.status_code == 401


def test_board_mutations_persist() -> None:
    browser = client()
    sign_in(browser)
    board = browser.get("/api/board").json()
    assert len(board["columns"]) == 5
    board = browser.put("/api/columns/col-backlog", json={"title": "Ideas"}).json()
    assert board["columns"][0]["title"] == "Ideas"
    board = browser.post("/api/cards", json={"column_id": "col-backlog", "title": "Persistent card", "details": "Saved"}).json()
    card_id = next(key for key, value in board["cards"].items() if value["title"] == "Persistent card")
    board = browser.post(f"/api/cards/{card_id}/move", json={"column_id": "col-review", "position": 0}).json()
    assert board["columns"][3]["cardIds"][0] == card_id
    board = browser.patch(f"/api/cards/{card_id}", json={"title": "Updated card"}).json()
    assert board["cards"][card_id]["title"] == "Updated card"
    board = browser.delete(f"/api/cards/{card_id}").json()
    assert card_id not in board["cards"]


def test_moving_a_card_within_a_column_reorders_it() -> None:
    browser = client()
    sign_in(browser)
    board = browser.post("/api/cards/card-1/move", json={"column_id": "col-backlog", "position": 1}).json()
    assert board["columns"][0]["cardIds"][:2] == ["card-2", "card-1"]


def test_repeated_cross_column_moves_preserve_order() -> None:
    browser = client()
    sign_in(browser)
    browser.post("/api/cards/card-1/move", json={"column_id": "col-review", "position": 0})
    board = browser.post("/api/cards/card-6/move", json={"column_id": "col-backlog", "position": 0}).json()
    assert board["columns"][0]["cardIds"][0] == "card-6"
    assert "card-1" in board["columns"][3]["cardIds"]


def test_invalid_board_mutation_does_not_change_the_board() -> None:
    browser = client()
    sign_in(browser)
    original = browser.get("/api/board").json()
    response = browser.post("/api/cards/card-1/move", json={"column_id": "missing", "position": 0})
    assert response.status_code == 404
    assert browser.get("/api/board").json() == original


# --- 422 validation paths (#18) ---

@pytest.mark.parametrize("title", ["", "   "])
def test_create_card_rejects_blank_title(title: str) -> None:
    browser = client()
    sign_in(browser)
    assert browser.post("/api/cards", json={"column_id": "col-backlog", "title": title}).status_code == 422


@pytest.mark.parametrize("title", ["", "   "])
def test_rename_column_rejects_blank_title(title: str) -> None:
    browser = client()
    sign_in(browser)
    assert browser.put("/api/columns/col-backlog", json={"title": title}).status_code == 422


def test_edit_card_rejects_blank_title() -> None:
    browser = client()
    sign_in(browser)
    assert browser.patch("/api/cards/card-1", json={"title": ""}).status_code == 422


def test_move_card_rejects_negative_position() -> None:
    browser = client()
    sign_in(browser)
    assert browser.post("/api/cards/card-1/move", json={"column_id": "col-backlog", "position": -1}).status_code == 422


def test_chat_rejects_empty_message() -> None:
    browser = client()
    sign_in(browser)
    assert browser.post("/api/chat", json={"message": ""}).status_code == 422


def test_chat_rejects_message_over_limit() -> None:
    browser = client()
    sign_in(browser)
    assert browser.post("/api/chat", json={"message": "x" * (_MAX_CHAT_MESSAGE_LEN + 1)}).status_code == 422


# --- Chat tests ---

class FakeOpenRouter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list = []

    async def complete_messages(self, messages: list) -> str:
        self.messages = messages
        return self.content


def test_chat_returns_no_op_response_and_board_context(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter(json.dumps({"version": 1, "message": "No changes needed.", "operations": []}))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = client()
    sign_in(browser)

    response = browser.post("/api/chat", json={"message": "What is on the board?"})

    assert response.status_code == 200
    assert response.json()["message"] == "No changes needed."
    assert fake.messages[-1] == {"role": "user", "content": "What is on the board?"}
    assert "col-backlog" in fake.messages[0]["content"]

    history = browser.get("/api/chat/history")
    assert history.status_code == 200
    assert history.json()["messages"][-1] == {"role": "assistant", "content": "No changes needed."}


def test_chat_applies_multiple_operations_atomically(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter(json.dumps({
        "version": 1,
        "message": "I updated the board.",
        "operations": [
            {"type": "rename_column", "column_id": "col-backlog", "title": "Ideas"},
            {"type": "create_card", "column_id": "col-backlog", "title": "AI card", "details": "Created by AI"},
        ],
    }))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = client()
    sign_in(browser)

    response = browser.post("/api/chat", json={"message": "Create an AI card."})

    assert response.status_code == 200
    board = response.json()["board"]
    assert board["columns"][0]["title"] == "Ideas"
    assert any(card["title"] == "AI card" for card in board["cards"].values())


def test_chat_rejects_malformed_model_output_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter("not JSON")
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = client()
    sign_in(browser)
    original = browser.get("/api/board").json()

    response = browser.post("/api/chat", json={"message": "Break the parser."})

    assert response.status_code == 502
    assert browser.get("/api/board").json() == original


def test_chat_rejects_invalid_operation_without_partial_update(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter(json.dumps({
        "version": 1,
        "message": "Attempted update.",
        "operations": [
            {"type": "rename_column", "column_id": "col-backlog", "title": "Ideas"},
            {"type": "delete_card", "card_id": "missing-card"},
        ],
    }))
    monkeypatch.setattr("app.main.openrouter_service", lambda: fake)
    browser = client()
    sign_in(browser)
    original = browser.get("/api/board").json()

    response = browser.post("/api/chat", json={"message": "Make invalid changes."})

    assert response.status_code == 422
    assert browser.get("/api/board").json() == original


def test_chat_history_is_bounded_to_20_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    browser = client()
    sign_in(browser)

    last_fake: FakeOpenRouter | None = None
    for i in range(25):
        content = json.dumps({"version": 1, "message": f"reply {i}", "operations": []})
        fake = FakeOpenRouter(content)
        monkeypatch.setattr("app.main.openrouter_service", lambda f=fake: f)
        browser.post("/api/chat", json={"message": f"message {i}"})
        last_fake = fake

    history = browser.get("/api/chat/history").json()
    assert len(history["messages"]) == 20

    assert last_fake is not None
    # system message + up to 20 history entries + current user message
    assert len(last_fake.messages) <= 22
