from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import numpy as np

from app.schema import Chunk


# ── VectorStore 数据模型 ──


class VectorItem:
    """单条向量 + 元数据"""

    def __init__(self, chunk_id: str, embedding: list[float], metadata: dict | None = None) -> None:
        self.chunk_id = chunk_id
        self.embedding = embedding
        self.metadata = metadata or {}


class VectorHit:
    """向量搜索结果"""

    def __init__(self, chunk_id: str, score: float) -> None:
        self.chunk_id = chunk_id
        self.score = score


# ── VectorStore 协议（详设 §5.2 冻结） ──


class VectorStore(Protocol):
    def upsert(self, items: list[VectorItem]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int, filters: dict | None = None) -> list[VectorHit]: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...


# ── LocalVectorStore（numpy 本地向量存储） ──


class LocalVectorStore:
    """基于 numpy 的本地向量存储（详设 §5.2 起步方案）"""

    _query_vector: np.ndarray
    _store_vectors: np.ndarray
    _chunk_ids: list[str]
    _chunk_id_to_idx: dict[str, int]

    def __init__(self, index_dir: Path) -> None:
        self._index_dir = index_dir
        index_dir.mkdir(parents=True, exist_ok=True)
        self._vectors_path = index_dir / "vectors.npy"
        self._ids_path = index_dir / "chunk_ids.json"
        self._load()

    # ── 公共接口 ──

    def upsert(self, items: list[VectorItem]) -> None:
        for item in items:
            vec = np.array(item.embedding, dtype=np.float32)
            if item.chunk_id in self._chunk_id_to_idx:
                idx = self._chunk_id_to_idx[item.chunk_id]
                self._store_vectors[idx] = vec
            else:
                idx = len(self._chunk_ids)
                self._chunk_ids.append(item.chunk_id)
                self._chunk_id_to_idx[item.chunk_id] = idx
                if idx == 0:
                    self._store_vectors = np.array([vec], dtype=np.float32)
                else:
                    self._store_vectors = np.vstack([self._store_vectors, vec])
        self._save()

    def search(self, query_embedding: list[float], top_k: int, filters: dict | None = None) -> list[VectorHit]:
        if len(self._chunk_ids) == 0:
            return []
        query_vec = np.array(query_embedding, dtype=np.float32)
        similarities = self._cosine_similarity(query_vec)
        effective_k = min(top_k, len(self._chunk_ids))
        top_indices = np.argsort(similarities)[-effective_k:][::-1]
        return [VectorHit(chunk_id=self._chunk_ids[int(i)], score=float(similarities[int(i)])) for i in top_indices]

    def delete(self, chunk_ids: list[str]) -> None:
        indices = [self._chunk_id_to_idx[cid] for cid in chunk_ids if cid in self._chunk_id_to_idx]
        if not indices:
            return
        mask = np.ones(len(self._chunk_ids), dtype=bool)
        mask[indices] = False
        self._chunk_ids = [self._chunk_ids[i] for i in range(len(self._chunk_ids)) if mask[i]]
        self._store_vectors = self._store_vectors[mask]
        self._chunk_id_to_idx = {cid: i for i, cid in enumerate(self._chunk_ids)}
        self._save()

    def count(self) -> int:
        return len(self._chunk_ids)

    def clear(self) -> None:
        self._chunk_ids = []
        self._store_vectors = np.array([], dtype=np.float32).reshape(0, 0)
        self._chunk_id_to_idx = {}
        self._save()

    # ── 内部方法 ──

    def _cosine_similarity(self, query_vec: np.ndarray) -> np.ndarray:
        if self._store_vectors.size == 0:
            return np.array([], dtype=np.float32)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        store_norms = self._store_vectors / (np.linalg.norm(self._store_vectors, axis=1, keepdims=True) + 1e-10)
        return np.dot(store_norms, query_norm)

    def _load(self) -> None:
        if self._vectors_path.exists() and self._ids_path.exists():
            self._store_vectors = np.load(str(self._vectors_path))
            self._chunk_ids = json.loads(self._ids_path.read_text(encoding="utf-8"))
            self._chunk_id_to_idx = {cid: i for i, cid in enumerate(self._chunk_ids)}
        else:
            self._store_vectors = np.array([], dtype=np.float32).reshape(0, 0)
            self._chunk_ids = []
            self._chunk_id_to_idx = {}

    def _save(self) -> None:
        np.save(str(self._vectors_path), self._store_vectors)
        self._ids_path.write_text(json.dumps(self._chunk_ids, ensure_ascii=False), encoding="utf-8")
