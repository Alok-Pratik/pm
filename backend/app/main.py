import asyncio
import logging
import os
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
    connect,
    do_move_card,
    get_board,
    initialize,
    owned_card,
    owned_column,
    recent_chat_messages,
    resolve_board,
    rewrite_positions,
    save_chat_message,
    write_connect,
)
from app.openrouter import OpenRouterError, OpenRouterService

logger = logging.getLogger(__name__)

_MAX_CHAT_MESSAGE_LEN = 2000


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with connect() as connection:
        initialize(connection)
    yield


app = FastAPI(title="Project Management MVP", lifespan=lifespan)

if not os.environ.get("SESSION_SECRET"):
    logger.warning(
        "SESSION_SECRET is not configured — sessions use a random per-process "
        "secret and will not survive a restart. Set SESSION_SECRET in your environment."
    )
_session_secret = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)

app.add_middleware(SessionMiddleware, secret_key=_session_secret)
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
    user = signed_in_user(request)
    with connect() as connection:
        board_id = resolve_board(connection, user)
        return get_board(connection, board_id)


@app.put("/api/columns/{column_id}")
def rename_column(column_id: str, update: ColumnUpdate, request: Request) -> dict:
    title = update.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Column title is required")
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = resolve_board(connection, user)
        owned_column(connection, column_id, board_id)
        connection.execute("UPDATE columns SET title = ? WHERE id = ?", (title, column_id))
        return get_board(connection, board_id)


@app.post("/api/cards")
def create_card(card: CardCreate, request: Request) -> dict:
    title = card.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Card title is required")
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = resolve_board(connection, user)
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


@app.patch("/api/cards/{card_id}")
def edit_card(card_id: str, update: CardUpdate, request: Request) -> dict:
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = resolve_board(connection, user)
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


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: str, request: Request) -> dict:
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = resolve_board(connection, user)
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


@app.post("/api/cards/{card_id}/move")
def move_card(card_id: str, move: CardMove, request: Request) -> dict:
    if move.position < 0:
        raise HTTPException(status_code=422, detail="Position must be zero or greater")
    user = signed_in_user(request)
    with write_connect() as connection:
        board_id = resolve_board(connection, user)
        do_move_card(connection, card_id, move.column_id, move.position, board_id)
        return get_board(connection, board_id)


@app.post("/api/chat")
async def chat(chat_request: ChatRequest, request: Request) -> dict:
    message = chat_request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is required")
    if len(message) > _MAX_CHAT_MESSAGE_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Message must be {_MAX_CHAT_MESSAGE_LEN} characters or fewer",
        )
    user = signed_in_user(request)

    def load_context() -> tuple[str, dict, list[dict]]:
        with connect() as connection:
            board_id = resolve_board(connection, user)
            return board_id, get_board(connection, board_id), recent_chat_messages(
                connection, user, board_id
            )

    board_id, board, history = await asyncio.to_thread(load_context)

    try:
        content = await openrouter_service().complete_messages(build_prompt(board, history, message))
        response = parse_ai_response(content)
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    def apply_changes() -> dict:
        with write_connect() as connection:
            board_id = resolve_board(connection, user)
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


@app.get("/api/chat/history")
def chat_history(request: Request) -> dict:
    user = signed_in_user(request)
    with connect() as connection:
        board_id = resolve_board(connection, user)
        return {"messages": recent_chat_messages(connection, user, board_id)}


if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
