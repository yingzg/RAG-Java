from __future__ import annotations

import json
from pathlib import Path

from app.schema import Chunk


class JsonlChunkStore:
    """Chunk 元数据存储（详设 §5.3 冻结）——扩展自 Day1.5 版本"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Chunk]:
        if not self.path.exists():
            raise FileNotFoundError(f"chunk index not found: {self.path}")
        chunks: list[Chunk] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                chunks.append(
                    Chunk(
                        chunk_id=item["chunk_id"],
                        source_name=item["source_name"],
                        source_root=item.get("source_root", ""),
                        source_path=item["source_path"],
                        file_name=item.get("file_name", ""),
                        section_path=item.get("section_path", ""),
                        chunk_index=int(item.get("chunk_index", 0)),
                        doc_type=item.get("doc_type", ""),
                        content=item["content"],
                        content_length=int(item.get("content_length", len(item["content"]))),
                        title=item.get("title", ""),
                        project=item.get("project", ""),
                        version=item.get("version", "v1"),
                        updated_at=item.get("updated_at", ""),
                        tags=item.get("tags", []),
                        doc_id=item.get("doc_id", ""),
                        content_hash=item.get("content_hash", ""),
                    )
                )
        return chunks

    def save(self, chunks: list[Chunk]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for c in chunks:
            lines.append(
                json.dumps(
                    {
                        "chunk_id": c.chunk_id,
                        "source_name": c.source_name,
                        "source_root": c.source_root,
                        "source_path": c.source_path,
                        "file_name": c.file_name,
                        "section_path": c.section_path,
                        "chunk_index": c.chunk_index,
                        "doc_type": c.doc_type,
                        "content": c.content,
                        "content_length": c.content_length,
                        "title": c.title,
                        "project": c.project,
                        "version": c.version,
                        "updated_at": c.updated_at,
                        "tags": c.tags,
                        "doc_id": c.doc_id,
                        "content_hash": c.content_hash,
                    },
                    ensure_ascii=False,
                )
            )
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get(self, chunk_id: str) -> Chunk | None:
        for chunk in self.load():
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def replace_docs(self, new_chunks: list[Chunk], removed_doc_ids: set[str]) -> None:
        """用新 chunk 替换指定文档的旧 chunk，删除 removed_doc_ids 的 chunk。"""
        existing = self.load()
        keep = [c for c in existing if c.doc_id not in removed_doc_ids]
        self.save(keep + new_chunks)

