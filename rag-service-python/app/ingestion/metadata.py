from __future__ import annotations

import hashlib
from pathlib import Path

DOC_TYPE_KEYWORDS = {
    "deep_dive": ["源码深度版", "深探版", "deep_dive"],
    "rebuild_guide": ["重建指南", "rebuild"],
    "knowledge": ["知识", "knowledge"],
    "architecture_guideline": ["架构", "architecture", "ddd", "dubbo"],
}

DOC_TYPE_FALLBACK = "index"


def extract_metadata(source_root: str, relative_path: str, content: str) -> dict:
    title = _extract_title(content)
    doc_type = _guess_doc_type(relative_path, title)
    doc_id = _hash_doc(source_root, relative_path)
    content_hash = _hash_text(content)
    return {
        "title": title,
        "doc_type": doc_type,
        "doc_id": doc_id,
        "content_hash": content_hash,
        "project": "",
        "version": "v1",
        "updated_at": "",
        "tags": [],
    }


def _extract_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 2:
            return stripped[2:].strip()
    return ""


def _guess_doc_type(relative_path: str, title: str) -> str:
    combined = f"{relative_path} {title}".lower()
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return doc_type
    return DOC_TYPE_FALLBACK


def _hash_doc(source_root: str, relative_path: str) -> str:
    return hashlib.sha256(f"{source_root}/{relative_path}".encode()).hexdigest()[:12]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
