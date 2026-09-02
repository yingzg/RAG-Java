from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.embedding.base import EmbeddingClient
from app.ingestion.chunker import chunk_document
from app.ingestion.loader import load_documents
from app.ingestion.metadata import extract_metadata
from app.schema import Chunk
from app.settings import Settings
from app.store.chunk_store import JsonlChunkStore
from app.store.vector_store import LocalVectorStore, VectorItem


class IndexService:
    def __init__(self, settings: Settings, embedding_client: EmbeddingClient,
                 chunk_store: JsonlChunkStore, vector_store: LocalVectorStore) -> None:
        self._settings = settings
        self._embedding = embedding_client
        self._chunk_store = chunk_store
        self._vector_store = vector_store

    def rebuild(self, source_names: list[str] | None = None) -> dict:
        started = time.perf_counter()
        trace_id = f"idx_{uuid4().hex[:12]}"
        docs = load_documents(self._settings.knowledge_sources, source_names)
        all_chunks = self._process_docs(docs)

        embeddings = self._embedding.embed_documents([c.content for c in all_chunks])
        vector_items = [VectorItem(chunk_id=c.chunk_id, embedding=emb) for c, emb in zip(all_chunks, embeddings)]

        if source_names:
            self._merge_chunks(all_chunks, source_names)
        else:
            self._chunk_store.save(all_chunks)
        self._vector_store.upsert(vector_items)

        return {
            "trace_id": trace_id,
            "type": "index_rebuild",
            "document_count": len(docs),
            "chunk_count": len(all_chunks),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def incremental(self, source_names: list[str] | None = None) -> dict:
        """增量索引：只处理新增/变更/删除的文档。"""
        started = time.perf_counter()
        trace_id = f"idx_{uuid4().hex[:12]}"

        docs = load_documents(self._settings.knowledge_sources, source_names)
        current_doc_ids = {_make_doc_id(d.source_root, d.relative_path): d for d in docs}

        existing_chunks = self._chunk_store.load()
        existing_by_doc: dict[str, list[Chunk]] = {}
        for c in existing_chunks:
            existing_by_doc.setdefault(c.doc_id, []).append(c)
        existing_doc_ids = set(existing_by_doc.keys())

        if source_names:
            existing_doc_ids = {
                doc_id for doc_id in existing_doc_ids
                if any(c.source_name in source_names for c in existing_by_doc[doc_id])
            }

        new_doc_ids = set(current_doc_ids.keys()) - existing_doc_ids
        deleted_doc_ids = existing_doc_ids - set(current_doc_ids.keys())

        changed_doc_ids = set()
        for doc_id, doc in current_doc_ids.items():
            if doc_id in existing_doc_ids:
                old_hash = existing_by_doc[doc_id][0].content_hash
                new_hash = extract_metadata(doc.source_root, doc.relative_path, doc.content)["content_hash"]
                if old_hash != new_hash:
                    changed_doc_ids.add(doc_id)

        docs_to_process = [current_doc_ids[doc_id] for doc_id in (new_doc_ids | changed_doc_ids)]
        new_chunks = self._process_docs(docs_to_process)

        chunk_ids_to_delete = [
            c.chunk_id for doc_id in (changed_doc_ids | deleted_doc_ids)
            for c in existing_by_doc.get(doc_id, [])
        ]

        if chunk_ids_to_delete:
            self._vector_store.delete(chunk_ids_to_delete)

        if new_chunks:
            embeddings = self._embedding.embed_documents([c.content for c in new_chunks])
            self._vector_store.upsert(
                [VectorItem(chunk_id=c.chunk_id, embedding=emb) for c, emb in zip(new_chunks, embeddings)]
            )

        self._chunk_store.replace_docs(new_chunks, sorted(changed_doc_ids | deleted_doc_ids))

        return {
            "trace_id": trace_id,
            "type": "index_incremental",
            "new_documents": len(new_doc_ids),
            "changed_documents": len(changed_doc_ids),
            "deleted_documents": len(deleted_doc_ids),
            "new_chunks": len(new_chunks),
            "deleted_chunks": len(chunk_ids_to_delete),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _process_docs(self, docs) -> list[Chunk]:
        chunks: list[Chunk] = []
        for doc in docs:
            meta = extract_metadata(doc.source_root, doc.relative_path, doc.content)
            raw_chunks = chunk_document(doc)
            for rc in raw_chunks:
                chunks.append(
                    Chunk(
                        chunk_id=_make_chunk_id(doc.source_name, doc.relative_path, rc["chunk_index"], rc["content"]),
                        source_name=doc.source_name,
                        source_root=doc.source_root,
                        source_path=doc.relative_path,
                        file_name=doc.file_name,
                        section_path=rc["section_path"],
                        chunk_index=rc["chunk_index"],
                        doc_type=meta["doc_type"],
                        content=rc["content"],
                        content_length=len(rc["content"]),
                        title=meta["title"],
                        project=meta["project"],
                        version=meta["version"],
                        updated_at=meta["updated_at"],
                        tags=meta["tags"],
                        doc_id=meta["doc_id"],
                        content_hash=meta["content_hash"],
                    )
                )
        return chunks

    def _merge_chunks(self, new_chunks: list[Chunk], source_names: list[str]) -> None:
        existing = self._chunk_store.load()
        keep = [c for c in existing if c.source_name not in source_names]
        self._chunk_store.save(keep + new_chunks)


def _make_chunk_id(source_name: str, relative_path: str, chunk_index: int, content: str) -> str:
    seed = f"{source_name}|{relative_path}|{chunk_index}|{content}"
    return f"{source_name}_{hashlib.sha256(seed.encode()).hexdigest()[:12]}"


def _make_doc_id(source_root: str, relative_path: str) -> str:
    return hashlib.sha256(f"{source_root}/{relative_path}".encode()).hexdigest()[:12]
