"""移植自 Day1.5 retrieval.py——详设 §5.4 冻结复用"""

from __future__ import annotations

from app.models import SearchFilters
from app.retrieval.base import QueryTokenizer, ScoredChunk
from app.schema import Chunk


class KeywordRetriever:
    """关键词检索器（多字段加权 + 可解释命中原因）"""

    def __init__(self) -> None:
        self.tokenizer = QueryTokenizer()

    def search(self, chunks: list[Chunk], query: str, top_k: int, filters=None) -> list[ScoredChunk]:
        tokens = self.tokenizer.tokenize(query)
        scored: list[ScoredChunk] = []
        for chunk in chunks:
            if filters:
                if hasattr(filters, 'source_name') and filters.source_name and chunk.source_name != filters.source_name:
                    continue
                if hasattr(filters, 'doc_type') and filters.doc_type and chunk.doc_type != filters.doc_type:
                    continue
            result = self._score(chunk, query, tokens)
            if result.score > 0:
                result.retriever = "keyword"
                scored.append(result)
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    def _score(self, chunk: Chunk, query: str, tokens: list[str]) -> ScoredChunk:
        score = 0.0
        matched_terms: list[str] = []
        reasons: list[str] = []
        lower_query = query.lower()
        lower_content = chunk.content.lower()
        lower_section = chunk.section_path.lower()
        lower_file = chunk.file_name.lower()
        lower_source = chunk.source_name.lower()

        if len(lower_query) >= 4 and lower_query in lower_content:
            score += 20
            matched_terms.append(query)
            reasons.append(f"完整查询命中正文")

        for token in tokens:
            lower_token = token.lower()
            if lower_token in lower_section:
                score += 8
                reasons.append(f"token '{token}' 命中标题: {chunk.section_path}")
            if lower_token in lower_file:
                score += 6
                reasons.append(f"token '{token}' 命中文件名: {chunk.file_name}")
            if lower_token in lower_source:
                score += 5
                reasons.append(f"token '{token}' 命中来源: {chunk.source_name}")
            content_hits = lower_content.count(lower_token)
            if content_hits:
                boost = min(12, content_hits * 2)
                score += boost
                reasons.append(f"token '{token}' 正文命中 {content_hits} 次 (+{boost})")
            if any(t in lower_section or t in lower_file or t in lower_source or t in lower_content for t in [lower_token]):
                if token not in matched_terms:
                    matched_terms.append(token)

        if score > 0 and chunk.doc_type in {"deep_dive", "rebuild_guide"}:
            score += 2
        elif score > 0 and chunk.doc_type == "index":
            score += 1

        return ScoredChunk(
            chunk=chunk,
            score=score,
            matched_terms=matched_terms,
            match_reasons=reasons,
            keyword_score=score,
        )
