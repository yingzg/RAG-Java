from __future__ import annotations

import re

from app.retrieval.base import ScoredChunk
from app.schema import Chunk


class CitationValidator:
    """两层校验：chunk_id 存在性 + 内容词级别匹配"""

    def validate(self, answer_text: str, contexts: list[ScoredChunk]) -> list[dict]:
        valid_chunk_ids = {item.chunk.chunk_id for item in contexts}
        chunk_map: dict[str, Chunk] = {item.chunk.chunk_id: item.chunk for item in contexts}
        answer_tokens = self._tokenize(answer_text)

        valid_citations: list[dict] = []
        for item in contexts:
            cid = item.chunk.chunk_id
            if cid not in valid_chunk_ids:
                continue
            chunk = chunk_map.get(cid)
            if chunk is None:
                continue
            # 词级别重叠校验：chunk 中有多少个实义词出现在答案中
            chunk_tokens = self._tokenize(chunk.content)
            overlap = answer_tokens & chunk_tokens
            if len(overlap) >= 2:
                valid_citations.append(
                    {
                        "chunk_id": cid,
                        "source_name": chunk.source_name,
                        "source_path": chunk.source_path,
                        "section_path": chunk.section_path,
                        "verified": True,
                    }
                )
        return valid_citations

    def all_valid(self, answer_text: str, contexts: list[ScoredChunk]) -> bool:
        return len(self.validate(answer_text, contexts)) > 0

    def _tokenize(self, text: str) -> set[str]:
        """提取实义词（长度≥2的中文词和英文词）"""
        tokens: set[str] = set()
        text_lower = text.lower()
        for match in re.finditer(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", text_lower):
            tokens.add(match.group(0))
        return tokens
