import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OperationType = Literal[
    "rename_column",
    "create_card",
    "edit_card",
    "delete_card",
    "move_card",
]


class BoardOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: OperationType
    column_id: str | None = None
    card_id: str | None = None
    title: str | None = None
    details: str | None = None
    position: int | None = Field(default=None, ge=0)


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


def build_prompt(board: dict, history: list[dict[str, str]], message: str) -> str:
    return json.dumps(
        {
            "instruction": (
                "Return only JSON matching this schema: {version: 1, message: string, "
                "operations: [{type, column_id?, card_id?, title?, details?, position?}]}. "
                "Use only the five supported operation types and valid IDs from the board. "
                "Do not include markdown."
            ),
            "board": board,
            "history": history[-20:],
            "user_message": message,
        }
    )