from __future__ import annotations

from dataclasses import dataclass, field

from app.generation.llm import LlmClient
from app.generation.prompt_builder import PromptBuilder
from app.retrieval.base import ScoredChunk


@dataclass
class GeneratedAnswer:
    text: str
    citations: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class AnswerGenerator:
    """答案生成器（详设 §5.5 冻结）"""

    def __init__(self, llm_client: LlmClient, prompt_builder: PromptBuilder) -> None:
        self._llm = llm_client
        self._prompt = prompt_builder

    def answer(self, question: str, contexts: list[ScoredChunk]) -> GeneratedAnswer:
        messages = self._prompt.build(question, contexts)
        result = self._llm.generate(messages, temperature=0.2, max_tokens=1024)

        citations = [{"chunk_id": item.chunk.chunk_id, "source_name": item.chunk.source_name, "source_path": item.chunk.source_path, "section_path": item.chunk.section_path} for item in contexts]

        return GeneratedAnswer(
            text=result.text,
            citations=citations,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
        )

    def has_llm(self) -> bool:
        """API key 为空时降级为模板回答"""
        try:
            self._llm.generate([], temperature=0, max_tokens=1)
            return True
        except Exception:
            return False
