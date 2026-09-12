import asyncio
import logging
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.ai import build_prompt, parse_ai_response
from app.config import OpenRouterSettings
from app.database import (
    NotFoundError,
    ValidationError,
    apply_board_operations,
    boards_for_user,
    connect,
    create_card_op,
    create_user,
    delete_card_op,
    do_move_card,
    edit_card_op,
    get_board,
    get_user_by_id,
    get_user_by_username,
    initialize,
    insert_board,
    owned_board,
    recent_chat_messages,
    remove_board,
    rename_column_op,
    require_nonblank,
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


@app.exception_handler(NotFoundError)
async def handle_not_found(_request: Request, error: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(ValidationError)
async def handle_validation_error(_request: Request, error: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(error)})


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


def require_board(connection: sqlite3.Connection, board_id: str, request: Request) -> tuple[str, sqlite3.Row]:
    """Verify the caller is signed in and owns board_id; raises 401/404 otherwise."""
    user = signed_in_user(request)
    board = owned_board(connection, board_id, user)
    return user, board


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
    with connect() as connection:
        _, board = require_board(connection, board_id, request)
        return {"id": board["id"], "title": board["title"], **get_board(connection, board_id)}


@app.patch("/api/boards/{board_id}")
def rename_board(board_id: str, payload: BoardRename, request: Request) -> dict:
    title = require_nonblank(payload.title, "Board title", max_len=_MAX_BOARD_TITLE_LEN)
    with write_connect() as connection:
        require_board(connection, board_id, request)
        update_board_title(connection, board_id, title)
        return {"id": board_id, "title": title, **get_board(connection, board_id)}


@app.delete("/api/boards/{board_id}")
def delete_board(board_id: str, request: Request) -> dict:
    with write_connect() as connection:
        user, _ = require_board(connection, board_id, request)
        remove_board(connection, board_id)
        return {"boards": boards_for_user(connection, user)}


@app.put("/api/boards/{board_id}/columns/{column_id}")
def rename_column(board_id: str, column_id: str, update: ColumnUpdate, request: Request) -> dict:
    with write_connect() as connection:
        require_board(connection, board_id, request)
        rename_column_op(connection, board_id, column_id, update.title)
        return get_board(connection, board_id)


@app.post("/api/boards/{board_id}/cards")
def create_card(board_id: str, card: CardCreate, request: Request) -> dict:
    with write_connect() as connection:
        require_board(connection, board_id, request)
        create_card_op(connection, board_id, card.column_id, card.title, card.details)
        return get_board(connection, board_id)


@app.patch("/api/boards/{board_id}/cards/{card_id}")
def edit_card(board_id: str, card_id: str, update: CardUpdate, request: Request) -> dict:
    with write_connect() as connection:
        require_board(connection, board_id, request)
        edit_card_op(connection, board_id, card_id, update.title, update.details)
        return get_board(connection, board_id)


@app.delete("/api/boards/{board_id}/cards/{card_id}")
def delete_card(board_id: str, card_id: str, request: Request) -> dict:
    with write_connect() as connection:
        require_board(connection, board_id, request)
        delete_card_op(connection, board_id, card_id)
        return get_board(connection, board_id)


@app.post("/api/boards/{board_id}/cards/{card_id}/move")
def move_card(board_id: str, card_id: str, move: CardMove, request: Request) -> dict:
    if move.position < 0:
        raise HTTPException(status_code=422, detail="Position must be zero or greater")
    with write_connect() as connection:
        require_board(connection, board_id, request)
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

    def load_context() -> tuple[str, dict, list[dict]]:
        with connect() as connection:
            user, _ = require_board(connection, board_id, request)
            return user, get_board(connection, board_id), recent_chat_messages(connection, user, board_id)

    user, board, history = await asyncio.to_thread(load_context)

    try:
        content = await openrouter_service().complete_messages(build_prompt(board, history, message))
        response = parse_ai_response(content)
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    def apply_changes() -> dict:
        with write_connect() as connection:
            require_board(connection, board_id, request)
            save_chat_message(connection, user, board_id, "user", message)
            try:
                apply_board_operations(connection, board_id, response.operations)
            except (NotFoundError, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            save_chat_message(connection, user, board_id, "assistant", response.message)
            return get_board(connection, board_id)

    board = await asyncio.to_thread(apply_changes)

    return {"version": response.version, "message": response.message, "board": board}


@app.get("/api/boards/{board_id}/chat/history")
def chat_history(board_id: str, request: Request) -> dict:
    with connect() as connection:
        user, _ = require_board(connection, board_id, request)
        return {"messages": recent_chat_messages(connection, user, board_id)}


if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
