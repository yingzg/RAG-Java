from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.settings import Settings


@dataclass
class LlmMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class LlmResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class LlmClient(Protocol):
    """LLM 客户端协议（详设 §5.5 冻结）"""

    def generate(self, messages: list[LlmMessage], temperature: float = 0.2, max_tokens: int = 1024) -> LlmResult: ...


class DeepSeekLlmClient:
    """DeepSeek LLM 客户端（OpenAI 兼容 API）"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, messages: list[LlmMessage], temperature: float = 0.2, max_tokens: int = 1024) -> LlmResult:
        openai_messages = [{"role": m.role, "content": m.content} for m in messages]
        with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
            response = client.post(
                f"{self._settings.llm_base_url}/chat/completions",
                json={
                    "model": self._settings.llm_model,
                    "messages": openai_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                headers={
                    "Authorization": f"Bearer {self._settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return LlmResult(
                text=choice["message"]["content"],
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model=data.get("model", self._settings.llm_model),
            )
