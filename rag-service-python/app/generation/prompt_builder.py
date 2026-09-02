from __future__ import annotations

from app.generation.llm import LlmMessage
from app.retrieval.base import ScoredChunk

PROMPT_VERSION = "rag_v1"

SYSTEM_PROMPT = """你是一个 Java 后端研发知识库助手。
你只能基于以下提供的引用文档片段回答问题。

规则：
1. 每个结论必须有引用来源（标注 chunk_id）。
2. 如果引用文档没有足够证据，必须明确说「根据当前资料无法确认」。
3. 不要编造文件路径、类名、接口、配置项或公司规范。
4. 涉及高风险操作时只给建议，不给出自动执行结论。
5. 回答结构：先给结论，再给依据，最后给建议。"""


class PromptBuilder:
    """Prompt 组装器（详设 §5.5 冻结）"""

    version: str = PROMPT_VERSION

    def build(self, question: str, contexts: list[ScoredChunk]) -> list[LlmMessage]:
        context_text = self._format_contexts(contexts)
        user_message = f"""## 用户问题
{question}

## 引用文档来源
{context_text}

请基于以上引用文档来源回答用户问题。"""
        return [
            LlmMessage(role="system", content=SYSTEM_PROMPT),
            LlmMessage(role="user", content=user_message),
        ]

    def _format_contexts(self, contexts: list[ScoredChunk]) -> str:
        parts = []
        for i, item in enumerate(contexts, start=1):
            chunk = item.chunk
            parts.append(
                f"""---
chunk_id: {chunk.chunk_id}
来源: {chunk.source_name}
路径: {chunk.source_path}
标题: {chunk.section_path}
相似度: {item.score:.3f}
---
{chunk.content}"""
            )
        return "\n".join(parts)
