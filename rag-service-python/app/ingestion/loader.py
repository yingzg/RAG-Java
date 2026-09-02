from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IGNORE_DIRS = {".git", ".vibe", ".vkf", "target", "node_modules", "__pycache__", ".github", ".idea"}

SUPPORTED_SUFFIXES = {".md", ".txt"}


@dataclass
class RawDocument:
    source_name: str
    source_root: str
    relative_path: str
    file_name: str
    content: str


def load_documents(sources: list[dict], source_names: list[str] | None = None) -> list[RawDocument]:
    """加载知识源文档。sources 为知识源定义列表（name/path/enabled）。"""
    docs: list[RawDocument] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        if source_names and src["name"] not in source_names:
            continue
        root = Path(src["path"])
        if not root.exists():
            continue
        for file_path in sorted(root.rglob("*")):
            if _should_skip(file_path):
                continue
            rel = file_path.relative_to(root)
            docs.append(
                RawDocument(
                    source_name=src["name"],
                    source_root=str(root),
                    relative_path=str(rel),
                    file_name=file_path.name,
                    content=file_path.read_text(encoding="utf-8"),
                )
            )
    return docs


def _should_skip(file_path: Path) -> bool:
    parts = set(file_path.parts)
    if parts & IGNORE_DIRS:
        return True
    return file_path.suffix.lower() not in SUPPORTED_SUFFIXES
