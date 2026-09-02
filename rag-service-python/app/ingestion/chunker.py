from __future__ import annotations

import re
from app.ingestion.loader import RawDocument

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 120


def chunk_document(doc: RawDocument) -> list[dict]:
    """
    按 Markdown 标题切块。
    返回 dict 列表，每个 dict 含 section_path / chunk_index / content / token_estimate 等。
    不依赖 Chunk dataclass——由 IndexService 组装。
    """
    sections = _split_by_headings(doc.content)
    chunks: list[dict] = []
    chunk_index = 0

    for section_path, section_text in sections:
        paragraphs = section_text.split("\n\n")
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if current and len(current) + len(para) < MAX_CHUNK_CHARS:
                current += "\n\n" + para
            else:
                if current:
                    for sub in _split_oversized(current):
                        chunks.append(
                            {
                                "section_path": section_path,
                                "chunk_index": chunk_index,
                                "content": _normalize(sub),
                            }
                        )
                        chunk_index += 1
                    current = para
                else:
                    current = para
        if current:
            for sub in _split_oversized(current):
                chunks.append(
                    {
                        "section_path": section_path,
                        "chunk_index": chunk_index,
                        "content": _normalize(sub),
                    }
                )
                chunk_index += 1

    chunks = _merge_short(chunks)
    for i, c in enumerate(chunks):
        c["chunk_index"] = i
    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    headings: list[str] = []
    sections: list[tuple[str, str]] = []
    last_end = 0

    for m in matches:
        if m.start() > last_end:
            prev_text = text[last_end : m.start()].strip()
            if prev_text:
                sections.append((" > ".join(headings) if headings else "", prev_text))

        level = len(m.group(1))
        title = m.group(2).strip()
        headings = headings[: level - 1] + [title]
        section_path = " > ".join(headings)
        last_end = m.end()

    if last_end < len(text):
        tail = text[last_end:].strip()
        if tail:
            sections.append((" > ".join(headings) if headings else "", tail))

    return sections


def _split_oversized(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    chunks = []
    for i in range(0, len(text), MAX_CHUNK_CHARS):
        chunks.append(text[i : i + MAX_CHUNK_CHARS])
    return chunks


def _merge_short(chunks: list[dict]) -> list[dict]:
    result = []
    for c in chunks:
        if result and len(c["content"]) < MIN_CHUNK_CHARS:
            prev = result[-1]
            merged = {**prev, "content": prev["content"] + "\n\n" + c["content"]}
            result[-1] = merged
        else:
            result.append(c)
    return result


def _normalize(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
