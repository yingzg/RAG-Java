"""规则 Reranker（详设 §5.4 冻结）——标题/路径/完整查询/doc_type 加权"""

from __future__ import annotations

from app.retrieval.base import QueryTokenizer, ScoredChunk

TITLE_WEIGHT = 0.30
FULL_QUERY_WEIGHT = 0.20
DOC_TYPE_WEIGHT = 0.10
ORIGINAL_SCORE_WEIGHT = 0.40
PREFERRED_TYPES = {"deep_dive", "architecture_guideline", "rebuild_guide"}


class RuleBasedReranker:
    def __init__(self) -> None:
        self._tokenizer = QueryTokenizer()

    def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        tokens = self._tokenizer.tokenize(query)
        lower_query = query.lower()

        for item in candidates:
            chunk = item.chunk
            rerank = item.score * ORIGINAL_SCORE_WEIGHT

            section_lower = chunk.section_path.lower()
            for token in tokens:
                if token.lower() in section_lower:
                    rerank += TITLE_WEIGHT
                    break

            if len(lower_query) >= 4 and lower_query in chunk.content.lower():
                rerank += FULL_QUERY_WEIGHT

            if chunk.doc_type in PREFERRED_TYPES:
                rerank += DOC_TYPE_WEIGHT

            item.rerank_score = rerank

        ranked = sorted(candidates, key=lambda item: item.rerank_score or 0, reverse=True)
        return ranked[:top_n]
