import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RenameColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["rename_column"]
    column_id: str
    title: str


class CreateCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["create_card"]
    column_id: str
    title: str
    details: str = ""


class EditCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["edit_card"]
    card_id: str
    title: str | None = None
    details: str | None = None


class DeleteCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["delete_card"]
    card_id: str


class MoveCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["move_card"]
    card_id: str
    column_id: str
    position: int = Field(ge=0)


BoardOperation = Annotated[
    RenameColumn | CreateCard | EditCard | DeleteCard | MoveCard,
    Field(discriminator="type"),
]


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    message: str = Field(min_length=1)
    operations: list[BoardOperation] = Field(default_factory=list, max_length=20)


def parse_ai_response(content: str) -> AIResponse:
    try:
        data = json.loads(content)
        return AIResponse.model_validate(data)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("AI returned an invalid structured response") from error


def build_prompt(board: dict, history: list[dict[str, str]], message: str) -> list[dict[str, str]]:
    system = (
        "You control a Kanban board. Return ONLY valid JSON matching this schema exactly: "
        '{"version": 1, "message": "<reply to user>", "operations": [...]}. '
        "Supported operation types and their required fields: "
        "rename_column (column_id, title), "
        "create_card (column_id, title, details?), "
        "edit_card (card_id, title?, details?), "
        "delete_card (card_id), "
        "move_card (card_id, column_id, position). "
        "Use only IDs that appear in the current board. The operations list may be empty. "
        "Do not include markdown, code fences, or any text outside the JSON object.\n\n"
        f"Current board state:\n{json.dumps(board)}"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    return messages
