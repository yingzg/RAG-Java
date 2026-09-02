from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schema import Chunk as SchemaChunk

STOP_WORDS = {
    "什么", "如何", "为什么", "怎么", "一下", "介绍", "说明", "请问",
    "帮我", "这个", "那个", "是否", "可以", "应该", "需要", "进行", "问题", "知识", "文档",
}


@dataclass
class ScoredChunk:
    """检索结果（详设 §4.2 冻结签名）"""
    chunk: SchemaChunk
    score: float
    matched_terms: list[str] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float | None = None
    retriever: str = ""


class QueryTokenizer:
    def tokenize(self, query: str) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()

        def add(token: str) -> None:
            if token and token not in STOP_WORDS and token not in seen:
                seen.add(token)
                tokens.append(token)

        for match in re.finditer(r"[A-Za-z][A-Za-z0-9_#.$-]*|[0-9]+", query):
            token = match.group(0)
            if len(token) >= 2:
                add(token)
                add(token.lower())

        chinese = re.sub(r"[A-Za-z0-9_#.$-]+", "", query)
        chinese = re.sub(r"\s+", "", chinese)
        for size in (2, 3):
            if len(chinese) < size:
                add(chinese)
                continue
            for index in range(0, len(chinese) - size + 1):
                add(chinese[index : index + size])
        return tokens
