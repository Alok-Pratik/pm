import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str
    model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    base_url: str = "https://openrouter.ai/api/v1"

    @classmethod
    def from_environment(cls) -> "OpenRouterSettings":
        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        return cls(api_key=api_key)