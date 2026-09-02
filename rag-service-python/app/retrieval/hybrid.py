"""RRF（Reciprocal Rank Fusion）Hybrid Retriever（详设 §5.4 冻结）"""

from __future__ import annotations

from app.models import SearchFilters
from app.retrieval.base import ScoredChunk
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.vector import VectorRetriever
from app.schema import Chunk

RRF_K = 60


class HybridRetriever:
    """混合检索器：关键词 + 向量 → RRF 融合 → 去重"""

    def __init__(self, keyword: KeywordRetriever, vector: VectorRetriever) -> None:
        self._keyword = keyword
        self._vector = vector

    def search(self, chunks: list[Chunk], query: str, top_k: int, filters: SearchFilters) -> list[ScoredChunk]:
        keyword_results = self._keyword.search(chunks, query, top_k=top_k * 2, filters=filters)
        vector_results = self._vector.search(query, top_k=top_k * 2)
        merged = self._rrf_fusion(keyword_results, vector_results)
        return merged[:top_k]

    def _rrf_fusion(self, keyword: list[ScoredChunk], vector: list[ScoredChunk]) -> list[ScoredChunk]:
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, ScoredChunk] = {}

        for rank, item in enumerate(keyword, start=1):
            cid = item.chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            item.keyword_score = item.score
            item.retriever = "hybrid"
            chunk_map[cid] = item

        for rank, item in enumerate(vector, start=1):
            cid = item.chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            if cid in chunk_map:
                chunk_map[cid].vector_score = item.vector_score
            else:
                item.vector_score = item.vector_score or item.score
                item.retriever = "hybrid"
                chunk_map[cid] = item

        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
        results = []
        for cid in sorted_ids:
            item = chunk_map[cid]
            item.score = rrf_scores[cid]
            results.append(item)
        return results
