"""
RAG 内部数据契约（详设 §4.1~§4.4 冻结签名）

所有 dataclass 按契约冻结版签名定义，三角色（R1/R2/R3）读写同一套数据结构。
新增字段全部带默认值，保证 prototype-cli 产出的旧 JSONL 可读。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── §4.1 Chunk（检索单元）───────────────────────────────────────────────


@dataclass(frozen=True)
class Chunk:
    """检索单元。字段与 prototype-cli 产出的 chunks.jsonl 向后兼容。"""

    # ── 现有字段（与 prototype chunks.jsonl 完全兼容）──
    chunk_id: str  # 全局唯一，如 "dubbo_94f3198f2530"
    source_name: str  # 知识源名：dubbo / ddd / state-machine / bff
    source_root: str  # 知识源根目录（绝对路径，可空）
    source_path: str  # 文档相对路径
    file_name: str  # 文件名
    section_path: str  # Markdown 标题路径（引用核心）
    chunk_index: int  # 文档内序号
    doc_type: str  # 文档类型：index / deep_dive / knowledge / rebuild_guide …
    content: str  # 正文
    content_length: int  # 字符数

    # ── §4.1 新增字段（默认值保证旧数据可读）──
    title: str = ""  # 文档标题
    project: str = ""  # 所属项目（多项目隔离用）
    version: str = "v1"  # 文档版本（防旧版污染）
    updated_at: str = ""  # 文档更新时间（ISO 8601）
    tags: list[str] = field(default_factory=list)  # 标签
    doc_id: str = ""  # 文档级 id（同文档多 chunk 共享）
    content_hash: str = ""  # 文档级内容哈希（增量索引用）


# ── §4.2 ScoredChunk（检索结果）───────────────────────────────────────────


@dataclass(frozen=True)
class ScoredChunk:
    """检索结果：chunk + 多维分数 + 命中解释"""

    chunk: Chunk
    score: float  # 归一化后的最终分（hybrid/rerank 后）

    matched_terms: list[str] = field(default_factory=list)  # 命中关键词
    match_reasons: list[str] = field(default_factory=list)  # 命中解释（trace 用）
    keyword_score: float = 0.0  # 关键词分支原始分
    vector_score: float = 0.0  # 向量分支原始分（cosine）
    rerank_score: float | None = None  # rerank 后分（无则 None）
    retriever: str = ""  # 来源：keyword / vector / hybrid


# ── §4.3 RagTrace（可观测性）───────────────────────────────────────────────


@dataclass
class TraceRetrievedChunk:
    """trace 中单个检索候选的详细信息"""
    chunk_id: str
    source_path: str
    score: float
    keyword_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float | None = None
    retriever: str = ""
    match_reasons: list[str] = field(default_factory=list)


@dataclass
class RagTrace:
    """每次 RAG 请求的流水账（详设 §4.3）"""

    trace_id: str
    type: str  # search / answer / eval
    question: str
    created_at: str = ""

    # 检索层
    query_rewritten: str | None = None
    filters: dict = field(default_factory=dict)
    retrieved_chunks: list[TraceRetrievedChunk] = field(
        default_factory=list
    )  # 候选：含 keyword/vector/rerank 分数
    final_context_chunk_ids: list[str] = field(default_factory=list)

    # 生成层
    prompt_version: str | None = None
    model: str | None = None
    answer: str | None = None
    citations: list[dict] = field(default_factory=list)

    # 拒答
    refused: bool = False
    refusal_reason: str | None = None

    # 性能
    latency_ms: int = 0
    tokens: dict = field(default_factory=dict)  # {"input":..., "output":...}

    # 结果
    success: bool = True
    error_type: str | None = None


# ── §4.4 EvalCase / EvalResult（质量评估）───────────────────────────────────


@dataclass
class EvalCase:
    """评估用例（兼容现有 rag_cases.jsonl 子集）"""

    id: str
    question: str
    expected_source_name: str | None = None  # 期望命中的知识源
    expected_sources: list[str] = field(default_factory=list)  # 期望文档路径
    expected_answer_points: list[str] = field(
        default_factory=list
    )  # 期望答案包含的关键要点
    should_refuse: bool = False  # 期望拒答
    risk: str = "normal"  # normal / high / critical


@dataclass
class EvalResult:
    """单条 eval 用例的执行结果"""

    case_id: str
    retrieval_hit: bool = False  # top-k 是否含期望来源
    recall_at_5: bool = False  # Recall@5
    recall_at_10: bool = False  # Recall@10
    mrr: float = 0.0  # 倒数排名
    answer_correct: bool | None = None  # 答案是否正确（无拒答时才评估）
    citation_correct: bool | None = None  # 引用是否真实
    refusal_correct: bool | None = None  # 拒答是否正确
    latency_ms: int = 0
    top_k_sources: list[str] = field(default_factory=list)
    error_type: str | None = None
