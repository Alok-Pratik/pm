import asyncio
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.ai import build_prompt, parse_ai_response
from app.config import OpenRouterSettings
from app.database import (
    apply_board_operations,
    boards_for_user,
    connect,
    create_user,
    do_move_card,
    get_board,
    get_user_by_id,
    get_user_by_username,
    initialize,
    insert_board,
    owned_board,
    owned_card,
    owned_column,
    recent_chat_messages,
    remove_board,
    rewrite_positions,
    save_chat_message,
    update_board_title,
    verify_password,
    write_connect,
)
from app.openrouter import OpenRouterError, OpenRouterService

logger = logging.getLogger(__name__)

_MAX_CHAT_MESSAGE_LEN = 2000
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_MIN_PASSWORD_LEN = 8
_MAX_PASSWORD_LEN = 128
_MAX_BOARD_TITLE_LEN = 100


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with connect() as connection:
        initialize(connection)
    yield


app = FastAPI(title="Project Management", lifespan=lifespan)

if not os.environ.get("SESSION_SECRET"):
    logger.warning(
        "SESSION_SECRET is not configured — sessions use a random per-process "
        "secret and will not survive a restart. Set SESSION_SECRET in your environment."
    )
_session_secret = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)

app.add_middleware(SessionMiddleware, secret_key=_session_secret)
frontend_dir = Path(__file__).parent / "static"


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class BoardCreate(BaseModel):
    title: str = "Untitled board"


class BoardRename(BaseModel):
    title: str


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
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/session")
def session(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if user_id:
        with connect() as connection:
            user = get_user_by_id(connection, user_id)
        if user:
            return {"authenticated": True, "username": user["username"]}
        request.session.clear()
    return {"authenticated": False}


@app.post("/api/auth/register")
def register(payload: RegisterRequest, request: Request) -> dict:
    username = payload.username.strip()
    if not _USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3-32 characters and may only contain letters, digits, '.', '_', or '-'",
        )
    if not (_MIN_PASSWORD_LEN <= len(payload.password) <= _MAX_PASSWORD_LEN):
        raise HTTPException(
            status_code=422,
            detail=f"Password must be between {_MIN_PASSWORD_LEN} and {_MAX_PASSWORD_LEN} characters",
        )
    with write_connect() as connection:
        if get_user_by_username(connection, username):
            raise HTTPException(status_code=409, detail="Username is already taken")
        user_id = create_user(connection, username, payload.password)
        insert_board(connection, user_id, "My board", seed=True)
    request.session["user_id"] = user_id
    return {"authenticated": True, "username": username}


@app.post("/api/auth/login")
def login(credentials: LoginRequest, request: Request) -> dict:
    with connect() as connection:
        user = get_user_by_username(connection, credentials.username.strip())
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session["user_id"] = user["id"]
    return {"authenticated": True, "username": user["username"]}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/boards")
def list_boards(request: Request) -> dict:
    user = signed_in_user(request)
    with connect() as connection:
        return {"boards": boards_for_user(connection, user)}


@app.post("/api/boards")
def create_board(payload: BoardCreate, request: Request) -> dict:
    title = payload.title.strip()[:_MAX_BOARD_TITLE_LEN] or "Untitled board"
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = insert_board(connection, user, title)
        return {"id": board_id, "title": title, **get_board(connection, board_id)}


@app.get("/api/boards/{board_id}")
def read_board(board_id: str, request: Request) -> dict:
    user = signed_in_user(request)
    with connect() as connection:
        board = owned_board(connection, board_id, user)
        return {"id": board["id"], "title": board["title"], **get_board(connection, board_id)}


@app.patch("/api/boards/{board_id}")
def rename_board(board_id: str, payload: BoardRename, request: Request) -> dict:
    title = payload.title.strip()[:_MAX_BOARD_TITLE_LEN]
    if not title:
        raise HTTPException(status_code=422, detail="Board title is required")
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        update_board_title(connection, board_id, title)
        return {"id": board_id, "title": title, **get_board(connection, board_id)}


@app.delete("/api/boards/{board_id}")
def delete_board(board_id: str, request: Request) -> dict:
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        remove_board(connection, board_id)
        return {"boards": boards_for_user(connection, user)}


@app.put("/api/boards/{board_id}/columns/{column_id}")
def rename_column(board_id: str, column_id: str, update: ColumnUpdate, request: Request) -> dict:
    title = update.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Column title is required")
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        owned_column(connection, column_id, board_id)
        connection.execute("UPDATE columns SET title = ? WHERE id = ?", (title, column_id))
        return get_board(connection, board_id)


@app.post("/api/boards/{board_id}/cards")
def create_card(board_id: str, card: CardCreate, request: Request) -> dict:
    title = card.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Card title is required")
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        owned_column(connection, card.column_id, board_id)
        position = connection.execute(
            "SELECT COUNT(*) FROM cards WHERE column_id = ?", (card.column_id,)
        ).fetchone()[0]
        card_id = f"card-{secrets.token_hex(4)}"
        connection.execute(
            "INSERT INTO cards (id, column_id, title, details, position) VALUES (?, ?, ?, ?, ?)",
            (card_id, card.column_id, title, card.details.strip(), position),
        )
        return get_board(connection, board_id)


@app.patch("/api/boards/{board_id}/cards/{card_id}")
def edit_card(board_id: str, card_id: str, update: CardUpdate, request: Request) -> dict:
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        card = owned_card(connection, card_id, board_id)
        title = card["title"] if update.title is None else update.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Card title is required")
        details = card["details"] if update.details is None else update.details.strip()
        connection.execute(
            "UPDATE cards SET title = ?, details = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, details, card_id),
        )
        return get_board(connection, board_id)


@app.delete("/api/boards/{board_id}/cards/{card_id}")
def delete_card(board_id: str, card_id: str, request: Request) -> dict:
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        card = owned_card(connection, card_id, board_id)
        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        remaining = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM cards WHERE column_id = ? ORDER BY position", (card["column_id"],)
            )
        ]
        rewrite_positions(connection, card["column_id"], remaining)
        return get_board(connection, board_id)


@app.post("/api/boards/{board_id}/cards/{card_id}/move")
def move_card(board_id: str, card_id: str, move: CardMove, request: Request) -> dict:
    if move.position < 0:
        raise HTTPException(status_code=422, detail="Position must be zero or greater")
    user = signed_in_user(request)
    with write_connect() as connection:
        owned_board(connection, board_id, user)
        do_move_card(connection, card_id, move.column_id, move.position, board_id)
        return get_board(connection, board_id)


@app.post("/api/boards/{board_id}/chat")
async def chat(board_id: str, chat_request: ChatRequest, request: Request) -> dict:
    message = chat_request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is required")
    if len(message) > _MAX_CHAT_MESSAGE_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Message must be {_MAX_CHAT_MESSAGE_LEN} characters or fewer",
        )
    user = signed_in_user(request)

    def load_context() -> tuple[dict, list[dict]]:
        with connect() as connection:
            owned_board(connection, board_id, user)
            return get_board(connection, board_id), recent_chat_messages(connection, user, board_id)

    board, history = await asyncio.to_thread(load_context)

    try:
        content = await openrouter_service().complete_messages(build_prompt(board, history, message))
        response = parse_ai_response(content)
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    def apply_changes() -> dict:
        with write_connect() as connection:
            owned_board(connection, board_id, user)
            save_chat_message(connection, user, board_id, "user", message)
            try:
                apply_board_operations(connection, board_id, response.operations)
            except (HTTPException, ValueError) as error:
                detail = error.detail if isinstance(error, HTTPException) else str(error)
                raise HTTPException(status_code=422, detail=detail) from error
            save_chat_message(connection, user, board_id, "assistant", response.message)
            return get_board(connection, board_id)

    board = await asyncio.to_thread(apply_changes)

    return {"version": response.version, "message": response.message, "board": board}


@app.get("/api/boards/{board_id}/chat/history")
def chat_history(board_id: str, request: Request) -> dict:
    user = signed_in_user(request)
    with connect() as connection:
        owned_board(connection, board_id, user)
        return {"messages": recent_chat_messages(connection, user, board_id)}


if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
