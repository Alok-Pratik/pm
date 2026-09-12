from typing import Any

import httpx

from app.config import OpenRouterSettings


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot provide a completion."""


class OpenRouterService:
    def __init__(self, settings: OpenRouterSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    async def complete(self, prompt: str) -> str:
        return await self.complete_messages([{"role": "user", "content": prompt}])

    async def complete_messages(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.settings.model,
            "messages": messages,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.base_url,
                headers=headers,
                timeout=30,
                transport=self.transport,
            ) as client:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise OpenRouterError("OpenRouter request failed") from error

        try:
            data: dict[str, Any] = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise OpenRouterError("OpenRouter returned an invalid response") from error

        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("OpenRouter returned an empty response")
        return content