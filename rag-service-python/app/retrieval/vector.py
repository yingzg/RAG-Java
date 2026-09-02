from __future__ import annotations

from app.embedding.base import EmbeddingClient
from app.retrieval.base import ScoredChunk
from app.schema import Chunk
from app.store.chunk_store import JsonlChunkStore
from app.store.vector_store import VectorStore


class VectorRetriever:
    """向量检索器（详设 §5.4）——embed_query → vector_store.search → ScoredChunk"""

    def __init__(self, embedding: EmbeddingClient, vector_store: VectorStore, chunk_store: JsonlChunkStore) -> None:
        self._embedding = embedding
        self._vector_store = vector_store
        self._chunk_store = chunk_store

    def search(self, query: str, top_k: int, filters: dict | None = None) -> list[ScoredChunk]:
        query_embedding = self._embedding.embed_query(query)
        hits = self._vector_store.search(query_embedding, top_k=top_k * 2, filters=filters)
        results: list[ScoredChunk] = []
        for hit in hits:
            chunk = self._chunk_store.get(hit.chunk_id)
            if chunk is not None:
                results.append(
                    ScoredChunk(
                        chunk=chunk,
                        score=hit.score,
                        vector_score=hit.score,
                        retriever="vector",
                    )
                )
        return results[:top_k]
