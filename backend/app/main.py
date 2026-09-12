import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.ai import build_prompt, parse_ai_response
from app.config import OpenRouterSettings
from app.database import apply_board_operations, connect, get_board, owned_card, owned_column, recent_chat_messages, rewrite_positions, save_chat_message
from app.openrouter import OpenRouterError, OpenRouterService

app = FastAPI(title="Project Management MVP")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "local-development-secret"),
)
frontend_dir = Path(__file__).parent / "static"


class LoginRequest(BaseModel):
    username: str
    password: str


class ColumnUpdate(BaseModel):
    title: str


class CardCreate(BaseModel):
    column_id: str
    title: str
    details: str = ""


class CardUpdate(BaseModel):
    title: str | None = None
    details: str | None = None


class CardMove(BaseModel):
    column_id: str
    position: int


class ChatRequest(BaseModel):
    message: str


def openrouter_service() -> OpenRouterService:
    try:
        return OpenRouterService(OpenRouterSettings.from_environment())
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def signed_in_user(request: Request) -> str:
    if request.session.get("user_id") != "user":
        raise HTTPException(status_code=401, detail="Authentication required")
    return "user"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hello")
def hello() -> dict[str, str]:
    return {"message": "Hello from FastAPI"}


@app.get("/api/auth/session")
def session(request: Request) -> dict[str, bool]:
    return {"authenticated": request.session.get("user_id") == "user"}


@app.post("/api/auth/login")
def login(credentials: LoginRequest, request: Request) -> dict[str, bool]:
    if credentials.username != "user" or credentials.password != "password":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    request.session["user_id"] = "user"
    return {"authenticated": True}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/board")
def read_board(request: Request) -> dict:
    with connect() as connection:
        return get_board(connection, signed_in_user(request))


@app.put("/api/columns/{column_id}")
def rename_column(column_id: str, update: ColumnUpdate, request: Request) -> dict:
    title = update.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Column title is required")
    with connect() as connection:
        owned_column(connection, column_id, signed_in_user(request))
        connection.execute("UPDATE columns SET title = ? WHERE id = ?", (title, column_id))
        return get_board(connection)


@app.post("/api/cards")
def create_card(card: CardCreate, request: Request) -> dict:
    title = card.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Card title is required")
    with connect() as connection:
        user = signed_in_user(request)
        owned_column(connection, card.column_id, user)
        position = connection.execute("SELECT COUNT(*) FROM cards WHERE column_id = ?", (card.column_id,)).fetchone()[0]
        card_id = f"card-{os.urandom(8).hex()}"
        connection.execute("INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)", (card_id, card.column_id, title, card.details.strip(), position))
        return get_board(connection, user)


@app.patch("/api/cards/{card_id}")
def edit_card(card_id: str, update: CardUpdate, request: Request) -> dict:
    with connect() as connection:
        user = signed_in_user(request)
        card = owned_card(connection, card_id, user)
        title = card["title"] if update.title is None else update.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Card title is required")
        details = card["details"] if update.details is None else update.details.strip()
        connection.execute("UPDATE cards SET title = ?, details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, details, card_id))
        return get_board(connection, user)


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: str, request: Request) -> dict:
    with connect() as connection:
        user = signed_in_user(request)
        card = owned_card(connection, card_id, user)
        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        card_ids = [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],))]
        rewrite_positions(connection, card["column_id"], card_ids)
        return get_board(connection, user)


@app.post("/api/cards/{card_id}/move")
def move_card(card_id: str, move: CardMove, request: Request) -> dict:
    if move.position < 0:
        raise HTTPException(status_code=422, detail="Position must be zero or greater")
    with connect() as connection:
        user = signed_in_user(request)
        card = owned_card(connection, card_id, user)
        owned_column(connection, move.column_id, user)
        source_ids = [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],))]
        target_ids = source_ids if card["column_id"] == move.column_id else [row["id"] for row in connection.execute("SELECT id FROM cards WHERE column_id = ? ORDER BY position", (move.column_id,))]
        source_ids.remove(card_id)
        target_ids = source_ids if card["column_id"] == move.column_id else target_ids
        target_ids.insert(min(move.position, len(target_ids)), card_id)
        if card["column_id"] == move.column_id:
            rewrite_positions(connection, move.column_id, target_ids)
        else:
            connection.execute("UPDATE cards SET position = 2000000, column_id = ? WHERE id = ?", (move.column_id, card_id))
            rewrite_positions(connection, card["column_id"], source_ids)
            rewrite_positions(connection, move.column_id, target_ids)
        return get_board(connection, user)


@app.post("/api/chat")
async def chat(chat_request: ChatRequest, request: Request) -> dict:
    message = chat_request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is required")
    user = signed_in_user(request)
    with connect() as connection:
        board = get_board(connection, user)
        history = recent_chat_messages(connection, user)

    try:
        content = await openrouter_service().complete(build_prompt(board, history, message))
        response = parse_ai_response(content)
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    try:
        with connect() as connection:
            save_chat_message(connection, user, "user", message)
            apply_board_operations(connection, user, [operation.model_dump(exclude_none=True) for operation in response.operations])
            save_chat_message(connection, user, "assistant", response.message)
            board = get_board(connection, user)
    except (HTTPException, ValueError) as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error

    return {"version": response.version, "message": response.message, "board": board}


@app.get("/api/chat/history")
def chat_history(request: Request) -> dict:
    user = signed_in_user(request)
    with connect() as connection:
        return {"messages": recent_chat_messages(connection, user)}


if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
