"""RAG 服务配置 — pydantic-settings 环境变量驱动（详设 §8 冻结）"""

from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ── 数据路径 ──
    data_dir: Path = Path("data")
    sources_config: Path = Path("config/sources.json")

    @property
    def chunk_index_path(self) -> Path:
        return self.data_dir / "index" / "chunks.jsonl"

    @property
    def vector_index_path(self) -> Path:
        return self.data_dir / "index"

    @property
    def trace_dir(self) -> Path:
        return self.data_dir / "traces"

    # ── Embedding（硅基流动 SiliconFlow） ──
    embedding_provider: str = "siliconflow"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = Field(default="", validation_alias="SILICONFLOW_API_KEY")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32

    # ── LLM（DeepSeek，OpenAI 兼容） ──
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    llm_model: str = "deepseek-chat"

    # ── Rerank ──
    rerank_enabled: bool = True
    rerank_top_n: int = 3
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # ── 向量存储（local / pgvector） ──
    vector_store: str = "local"

    # ── 检索/生成参数 ──
    top_k: int = 8
    rerank_candidate_k: int = 20
    refuse_score_threshold: float = 0.01

    # ── 知识源 ──
    source_names: list[str] = ["java", "ai", "other"]

    # ── 知识库根目录（独立于 RAG 工具，环境变量 KNOWLEDGE_BASE_DIR 可配置） ──
    knowledge_base_dir: Path = Field(
        default=Path("data/knowledge"),
        validation_alias="KNOWLEDGE_BASE_DIR",
    )

    @property
    def knowledge_sources(self) -> list[dict]:
        """三类知识源：目录由 knowledge_base_dir 动态生成。"""
        return [
            {"name": "java", "path": str(self.knowledge_base_dir / "java"), "enabled": True},
            {"name": "ai", "path": str(self.knowledge_base_dir / "ai"), "enabled": True},
            {"name": "other", "path": str(self.knowledge_base_dir / "other"), "enabled": True},
        ]

    @property
    def category_dirs(self) -> dict[str, Path]:
        """分类名 → 分类目录（上传接口用）"""
        return {
            "java": self.knowledge_base_dir / "java",
            "ai": self.knowledge_base_dir / "ai",
            "other": self.knowledge_base_dir / "other",
        }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "index").mkdir(parents=True, exist_ok=True)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        for category_dir in self.category_dirs.values():
            category_dir.mkdir(parents=True, exist_ok=True)
