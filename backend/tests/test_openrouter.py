import json

import httpx
import pytest

from app.config import OpenRouterSettings
from app.openrouter import OpenRouterError, OpenRouterService


@pytest.mark.anyio
async def test_complete_builds_openrouter_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "4"}}]})

    service = OpenRouterService(
        OpenRouterSettings(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    assert await service.complete("2+2") == "4"
    assert requests[0].url == "https://openrouter.ai/api/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(requests[0].content) == {
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "messages": [{"role": "user", "content": "2+2"}],
    }


def test_missing_key_is_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is not configured"):
        OpenRouterSettings.from_environment()


@pytest.mark.anyio
async def test_upstream_failure_is_safe_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    service = OpenRouterService(
        OpenRouterSettings(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError, match="OpenRouter request failed"):
        await service.complete("2+2")


@pytest.mark.anyio
async def test_malformed_response_is_safe_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    service = OpenRouterService(
        OpenRouterSettings(api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OpenRouterError, match="invalid response"):
        await service.complete("2+2")