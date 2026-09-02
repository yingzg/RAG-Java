# 中级 RAG 个人知识库 · 开发详设（Phase 0）

> 日期：2026-06-24
> 状态：契约冻结版（本文件冻结后，Phase 1~3 三角色才允许并发实施）
> 适用：基于现有 `RAG-Java` 改造为可部署的中级 RAG 个人问答知识库，兼顾面试讲解。

---

## 0. 本文档的作用

这是一份"**契约优先**"的开发详设。它的核心目的不是描述功能，而是把**模块边界、数据模型、接口签名、API/MCP 契约、配置、部署**钉死，使得：

- 索引+检索、生成+服务、质量+集成 三条线可以在各自 worktree 里**并发开发而不互相返工**；
- 用户（10 年 Java 背景、不熟 Python）能用 Java 原型对照理解 Python 实现；
- 最终产物可用 Docker Compose 部署到 2核2G 云服务器，通过 HTTP / MCP 访问。

> 原则：**Phase 0 冻结接口 → Phase 1~3 并发实现 → 按序合并。** 接口未冻结前不写实现；接口变更必须回到本文件先改契约。

---

## 1. 决策基线（已与用户对齐，不再讨论）

| 维度 | 决策 |
|---|---|
| 正式服务语言 | Python 3.12 + FastAPI（复用 `rag-service-python`） |
| Java `prototype-cli` | 保留为学习对照，能力对等后再删 |
| MCP 适配 | TypeScript `rag-mcp-server`，薄转发层，只调 HTTP |
| LLM 生成 | DeepSeek（OpenAI 兼容），client 可配，后续可切小米 MiMo |
| Embedding | 硅基流动 SiliconFlow，`BAAI/bge-m3`（1024 维） |
| Rerank（可选） | 硅基流动 `BAAI/bge-reranker-v2-m3`（有就用，否则规则 rerank） |
| 向量存储 | 起步轻量（SQLite + 本地向量文件），`VectorStore` 接口可切 pgvector |
| 部署 | Docker Compose，`python:3.12-slim`，2G 守内存纪律 |
| 对外访问 | HTTP API + MCP |
| 角色 | 3 角色：R1 索引+检索 / R2 生成+服务 / R3 质量+集成 |
| 协作流 | superpowers；worktree：Phase 0 单 worktree 定契约 → 阶段内 `git-worktree-multi-task` 三路并发 → 按序合并 |

服务器硬约束（已据此砍方案）：2核 CPU / 2G 内存 / 40G 盘 / 无 GPU / Docker 待装。
→ **已排除**：Elasticsearch、服务器本地跑 LLM、服务器本地跑大 embedding 模型。
→ 模型全部走云端 API，服务器只发 HTTP。

---

## 2. 总体架构

### 2.1 组件视图

```text
                          知识源（Markdown 技术文档）
                          dubbo / ddd / state-machine / bff ...
                                      |
                                      v
            ┌─────────────────────────────────────────────┐
            │            rag-service-python (FastAPI)        │
            │                                                │
            │  [离线索引链路]                                 │
            │   ingestion → chunking → metadata              │
            │     → EmbeddingClient → VectorStore            │
            │     → ChunkStore(元数据)                        │
            │                                                │
            │  [在线问答链路]                                 │
            │   query → (QueryRewriter)                       │
            │     → KeywordRetriever ┐                        │
            │     → VectorRetriever  ├→ HybridRetriever       │
            │                        ┘   → Reranker           │
            │     → PromptBuilder → AnswerGenerator(LLM)      │
            │     → CitationValidator → RefusalPolicy         │
            │     → TraceRecorder / EvalRunner                │
            └───────────────┬───────────────┬────────────────┘
                            │               │
                   ┌────────┘               └────────┐
                   v                                  v
        SiliconFlow Embedding/Rerank API      DeepSeek LLM API
                   |
                   v
        VectorStore: 本地文件/SQLite（起步）→ pgvector（可选升级）

外部调用方：
   rag-mcp-server (TS, MCP) ──HTTP──> rag-service-python
   Agent / IDE / Skill / 浏览器 / curl ──HTTP/MCP──> 同上
```

### 2.2 部署视图（Docker Compose，2核2G）

```text
docker-compose.yml
 ├─ rag-service     (python:3.12-slim, uvicorn, 暴露 8000)
 │     volume: ./data  (chunks 索引 / 向量文件 / traces / eval 报告)
 │     env:   DEEPSEEK_API_KEY / SILICONFLOW_API_KEY / 配置项
 └─ rag-mcp         (node:20-slim, 可选；MCP over stdio 或 HTTP)
       env:   RAG_SERVICE_BASE_URL=http://rag-service:8000

内存预算（粗算）：rag-service ~250-400MB + rag-mcp ~80MB + 系统/Docker ~300MB
→ 2G 可容纳；pgvector 若启用再单评估，起步不启用。
```

---

## 3. 改造后的仓库目录结构

```text
RAG-Java/
├─ prototype-cli/            # Java 学习原型（保留，作对照讲解，暂不删）
├─ rag-service-python/       # 正式服务（本轮主战场）
│  ├─ app/
│  │  ├─ main.py             # FastAPI 入口（已存在，扩展路由）
│  │  ├─ settings.py         # 配置（重写：支持多 provider / vectorstore 切换）
│  │  ├─ models.py           # API 请求/响应模型（已存在，扩展字段）
│  │  ├─ schema.py           # ★新增 内部数据契约：Chunk/Document/Trace/EvalCase
│  │  ├─ ingestion/          # ★R1 离线索引链路
│  │  │  ├─ loader.py        #   Markdown 加载（移植 prototype MarkdownLoader）
│  │  │  ├─ chunker.py       #   标题切块（移植 MarkdownChunker）
│  │  │  ├─ metadata.py      #   metadata 提取
│  │  │  └─ index_service.py #   编排：load→chunk→embed→store
│  │  ├─ embedding/          # ★R1
│  │  │  ├─ base.py          #   EmbeddingClient 抽象
│  │  │  └─ siliconflow.py   #   SiliconFlow 实现
│  │  ├─ store/              # ★R1
│  │  │  ├─ chunk_store.py   #   chunk 元数据存储（JSONL/SQLite）
│  │  │  ├─ vector_store.py  #   VectorStore 抽象
│  │  │  ├─ local_vector.py  #   本地文件/numpy 实现（起步）
│  │  │  └─ pgvector.py      #   预留（Phase 后期/可选）
│  │  ├─ retrieval/          # ★R1
│  │  │  ├─ base.py          #   Retriever 抽象 + ScoredChunk
│  │  │  ├─ keyword.py       #   关键词检索（移植现有 retrieval.py）
│  │  │  ├─ vector.py        #   向量检索
│  │  │  ├─ hybrid.py        #   混合检索（RRF/加权融合）
│  │  │  └─ reranker.py      #   规则 rerank + 可选模型 rerank
│  │  ├─ generation/         # ★R2
│  │  │  ├─ llm.py           #   LlmClient 抽象 + DeepSeek 实现
│  │  │  ├─ prompt_builder.py
│  │  │  ├─ answer_generator.py
│  │  │  ├─ citation.py      #   CitationValidator
│  │  │  └─ refusal.py       #   RefusalPolicy
│  │  ├─ service.py          # ★R2 应用编排（已存在，重构为依赖注入各组件）
│  │  ├─ trace/              # ★R3
│  │  │  └─ recorder.py      #   TraceRecorder
│  │  └─ eval/               # ★R3
│  │     ├─ runner.py        #   EvalRunner
│  │     └─ report.py        #   报告生成
│  ├─ data/                  # 运行数据（索引/向量/traces/eval）
│  ├─ tests/                 # pytest（各角色自带单测）
│  ├─ pyproject.toml
│  └─ Dockerfile            # ★R2
├─ rag-mcp-server/           # ★R3 TS MCP（已存在，对齐新 API）
├─ docker-compose.yml        # ★R2
├─ eval/                     # 共享 eval case 与报告
└─ docs/
   └─ 中级RAG-开发详设.md     # 本文件
```

★ 标注了三角色的主要责任目录，详见 §10。

---

## 4. 数据模型契约（冻结）

> 这是并发的第一基石。所有角色读写同一套数据结构。字段尽量复用现有 `prototype-cli` / `rag-service-python` 已有 schema，仅做**向后兼容的扩展**。

### 4.1 Chunk（检索单元）

`app/schema.py`：

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Chunk:
    # —— 现有字段（与 prototype chunks.jsonl 完全兼容）——
    chunk_id: str          # 全局唯一，如 "dubbo_94f3198f2530"
    source_name: str       # 知识源：dubbo / ddd / state-machine / bff
    source_root: str       # 知识源根目录（绝对路径，可空）
    source_path: str       # 文档相对路径
    file_name: str         # 文件名
    section_path: str      # Markdown 标题路径（引用核心）
    chunk_index: int       # 文档内序号
    doc_type: str          # 文档类型：index/deep_dive/knowledge/rebuild_guide...
    content: str           # 正文
    content_length: int

    # —— 中级新增字段（默认值保证旧数据可读）——
    title: str = ""                 # 文档标题
    project: str = ""               # 所属项目（多项目隔离用）
    version: str = "v1"             # 文档版本（防旧版污染）
    updated_at: str = ""            # 文档更新时间
    tags: list[str] = field(default_factory=list)
    doc_id: str = ""                # 文档级 id（同文档多 chunk 共享）
    content_hash: str = ""          # 文档级内容哈希（增量索引用）
```

> embedding 向量**不存在 Chunk 里**，而是由 `VectorStore` 按 `chunk_id` 单独管理，便于换模型重建。

### 4.2 ScoredChunk（检索结果）

`app/retrieval/base.py`：

```python
@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float                       # 归一化后的最终分（hybrid/rerank 后）
    matched_terms: list[str]           # 命中关键词（keyword 分支产出）
    match_reasons: list[str] = field(default_factory=list)  # 命中解释（trace 用）
    keyword_score: float = 0.0         # 关键词分支原始分
    vector_score: float = 0.0          # 向量分支原始分（cosine）
    rerank_score: float | None = None  # rerank 后分（无则 None）
    retriever: str = ""                # 来源：keyword/vector/hybrid
```

### 4.3 Trace（可观测性，扩展现有 trace JSON）

```python
@dataclass
class RagTrace:
    trace_id: str
    type: str                  # search / answer / eval
    question: str
    query_rewritten: str | None
    filters: dict
    retrieved_chunks: list[dict]   # 候选：chunk_id/score/keyword/vector/rerank/reasons
    final_context_chunk_ids: list[str]
    prompt_version: str | None
    model: str | None
    answer: str | None
    citations: list[dict]
    refused: bool
    refusal_reason: str | None
    latency_ms: int
    tokens: dict                   # {"input":..,"output":..}
    success: bool
    error_type: str | None
    created_at: str
```

trace 落盘：`data/traces/{trace_id}.json`（沿用现有方式），可查询。

### 4.4 EvalCase / EvalResult（扩展现有 rag_cases.jsonl）

```python
@dataclass
class EvalCase:
    id: str
    question: str
    expected_source_name: str | None   # 期望命中的知识源
    expected_sources: list[str] = field(default_factory=list)  # 期望文档路径
    expected_answer_points: list[str] = field(default_factory=list)
    should_refuse: bool = False
    risk: str = "normal"               # normal/high/critical

@dataclass
class EvalResult:
    case_id: str
    retrieval_hit: bool        # top-k 是否含期望来源
    answer_correct: bool | None
    citation_correct: bool | None
    refusal_correct: bool | None
    latency_ms: int
    top_k_sources: list[str]
    error_type: str | None
```

> 现有 `rag_cases.jsonl`（`{id,question,expected_source_name,should_refuse}`）是本结构的子集，可直接读。

---

## 5. 核心接口契约（冻结）

> 这是并发的第二基石。三角色面向**接口**编程；实现可独立替换。Python 用 `Protocol`/`ABC` 表达。

### 5.1 EmbeddingClient（R1）

```python
class EmbeddingClient(Protocol):
    @property
    def model(self) -> str: ...
    @property
    def dimension(self) -> int: ...        # bge-m3 = 1024
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

- 实现 `SiliconFlowEmbeddingClient`：调 `POST {base_url}/embeddings`，OpenAI 兼容。
- 批量分批（每批 ≤ 32），失败重试，速率限制保护。

### 5.2 VectorStore（R1）

```python
@dataclass
class VectorItem:
    chunk_id: str
    embedding: list[float]
    metadata: dict          # source_name/doc_type/project/version 等，供过滤

@dataclass
class VectorHit:
    chunk_id: str
    score: float            # cosine 相似度 [-1,1] 或 [0,1]

class VectorStore(Protocol):
    def upsert(self, items: list[VectorItem]) -> None: ...
    def search(self, query_embedding: list[float], top_k: int,
               filters: dict | None = None) -> list[VectorHit]: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...
```

- 起步实现 `LocalVectorStore`：向量存 `data/index/vectors.npy` + `chunk_id` 映射，numpy 算 cosine。
- 预留 `PgVectorStore`（同接口），Phase 后期可切，不影响上层。

### 5.3 ChunkStore（R1）

```python
class ChunkStore(Protocol):
    def save(self, chunks: list[Chunk]) -> None: ...
    def load(self) -> list[Chunk]: ...
    def get(self, chunk_id: str) -> Chunk | None: ...
```

- 起步 `JsonlChunkStore`（复用现有 `store.py`，扩展新字段读取，缺字段用默认值）。

### 5.4 Retriever / Reranker（R1）

```python
class Retriever(Protocol):
    def search(self, query: str, top_k: int, filters: dict) -> list[ScoredChunk]: ...

class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[ScoredChunk],
               top_n: int) -> list[ScoredChunk]: ...
```

- `KeywordRetriever`：移植现有 `retrieval.py`（已实现，质量不错，直接复用）。
- `VectorRetriever`：`EmbeddingClient.embed_query` → `VectorStore.search` → 映射成 `ScoredChunk`。
- `HybridRetriever`：组合 keyword + vector，用 **RRF（Reciprocal Rank Fusion）** 融合（默认），去重，输出候选。
- `RuleBasedReranker`：标题命中/路径命中/原词命中/doc_type/向量分 加权；可选 `ModelReranker`（SiliconFlow bge-reranker）。

### 5.5 生成链（R2）

```python
@dataclass
class LlmMessage:
    role: str   # system/user/assistant
    content: str

@dataclass
class LlmResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str

class LlmClient(Protocol):
    def generate(self, messages: list[LlmMessage],
                 temperature: float = 0.2, max_tokens: int = 1024) -> LlmResult: ...

class PromptBuilder(Protocol):
    version: str
    def build(self, question: str, contexts: list[ScoredChunk]) -> list[LlmMessage]: ...

class AnswerGenerator(Protocol):
    def answer(self, question: str, contexts: list[ScoredChunk]) -> "GeneratedAnswer": ...

class CitationValidator(Protocol):
    # 校验答案引用确实来自给定上下文，过滤幻觉引用
    def validate(self, answer_text: str, contexts: list[ScoredChunk]) -> list[dict]: ...

class RefusalPolicy(Protocol):
    # 返回 (是否拒答, 原因)
    def should_refuse(self, question: str, contexts: list[ScoredChunk]) -> tuple[bool, str | None]: ...
```

- `DeepSeekLlmClient`：调 `POST {base_url}/chat/completions`，OpenAI 兼容，`model=deepseek-chat`。
- 在线问答编排顺序（service.py）：
  `RefusalPolicy(前置敏感词/低分) → PromptBuilder → LlmClient → CitationValidator → RefusalPolicy(后置无有效引用)`。

### 5.6 IndexService（R1，离线编排）

```python
class IndexService:
    def rebuild(self, source_names: list[str], mode: str = "full") -> IndexRebuildResponse:
        # load → chunk → metadata → embed_documents → vector_store.upsert + chunk_store.save
        ...
```

---

## 6. HTTP API 契约（冻结，扩展现有）

基础路径 `/api/v1`。复用现有 5 个端点的 **请求/响应外形**，仅在响应里**新增可选字段**（向后兼容）。

| 端点 | 方法 | 说明 | 本轮变化 |
|---|---|---|---|
| `/health` | GET | 健康检查 | 不变 |
| `/api/v1/index/rebuild` | POST | 重建索引 | **真实现**（含 embedding）|
| `/api/v1/search` | POST | 检索 | 新增 hybrid，`SearchHit` 增 `vector_score/rerank_score/retriever` |
| `/api/v1/answer` | POST | 问答 | 接 LLM；`AnswerResponse` 增 `tokens`/`refusal_reason` |
| `/api/v1/traces/{trace_id}` | GET | 查 trace | 字段扩展（§4.3）|
| `/api/v1/eval/run` | POST | 跑 eval | **真实现** |

`SearchRequest` 扩展（`models.py`）：

```python
class SearchFilters(BaseModel):
    source_name: str | None = None
    doc_type: str | None = None
    project: str | None = None      # 新增
    version: str | None = None      # 新增

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: SearchFilters = SearchFilters()
    mode: str = "hybrid"            # 新增：keyword/vector/hybrid
    rerank: bool = True             # 新增
    include_content: bool = True
```

> 约束：**字段只增不删不改类型**，保证 MCP（R3）与服务（R2）可并行。

---

## 7. MCP Tool 契约（冻结，复用现有设计）

沿用 `docs/mcp-tool-design.md`：`doc.search` → `/search`，`rag.answer` → `/answer`，`rag.eval.run` → `/eval/run`。R3 仅需对齐 §6 的新字段，MCP 自身不含 RAG 逻辑。

---

## 8. 配置设计（冻结）

`app/settings.py` 重写为环境变量驱动（pydantic-settings），**模型供应商解耦**：

```python
class Settings(BaseSettings):
    # 数据路径
    data_dir: Path = Path("data")
    chunk_index_path: Path = data_dir / "index" / "chunks.jsonl"
    vector_index_path: Path = data_dir / "index" / "vectors.npy"
    trace_dir: Path = data_dir / "traces"

    # 知识源
    sources_config: Path = Path("config/sources.json")

    # Embedding（硅基流动）
    embedding_provider: str = "siliconflow"
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = ""          # 环境变量 SILICONFLOW_API_KEY
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # LLM（DeepSeek）
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""                # 环境变量 DEEPSEEK_API_KEY
    llm_model: str = "deepseek-chat"

    # Rerank（可选）
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # 向量存储
    vector_store: str = "local"          # local / pgvector

    # 检索/生成参数
    top_k: int = 8
    rerank_top_n: int = 3
    refuse_score_threshold: float = 0.30  # 向量相似度阈值（低于则拒答）
```

> answer 链路在 `llm_api_key` 为空时**自动降级**为模板化回答（兼容"先不接 LLM"场景）；现已有 DeepSeek key，默认真跑。

---

## 9. 数据流（冻结）

### 9.1 离线索引

```text
sources.json 配置的知识源目录
  → MarkdownLoader 加载 .md（排除 .git/.vibe/.vkf/target/node_modules）
  → MarkdownChunker 标题切块（保留 section_path/source_path）
  → MetadataExtractor 补 title/project/version/doc_id/content_hash/tags
  → EmbeddingClient.embed_documents 批量向量化
  → VectorStore.upsert + ChunkStore.save
```

### 9.2 在线问答

```text
question
  → (QueryRewriter 可选，Phase 后期)
  → KeywordRetriever.search ┐
  → VectorRetriever.search  ├→ HybridRetriever(RRF 融合, 去重) top_k
  → RuleBasedReranker.rerank → top_n
  → RefusalPolicy 前置（敏感词 / 最高分 < 阈值 → 拒答）
  → PromptBuilder.build（含规则/上下文/引用格式/拒答规则）
  → LlmClient.generate
  → CitationValidator.validate（剔除幻觉引用）
  → RefusalPolicy 后置（无有效引用 → 拒答）
  → TraceRecorder 落盘
  → AnswerResponse（answer + citations + tokens + trace_id）
```

---

## 10. 三角色任务划分 + 并发执行（冻结）

> 契约（§4~§9）冻结后，三角色在各自 worktree 并发。每角色**只改自己目录**，跨目录只依赖本文件定义的接口。

### R1 索引 + 检索
- 目录：`ingestion/ embedding/ store/ retrieval/`
- 产出：MarkdownLoader/Chunker/Metadata、SiliconFlowEmbeddingClient、LocalVectorStore、JsonlChunkStore、Keyword/Vector/Hybrid Retriever、RuleBasedReranker、IndexService。
- 对外承诺：实现 §5.1~5.6(检索部分) 接口；`/index/rebuild`、`/search` 真跑通。

### R2 生成 + 服务
- 目录：`generation/ service.py main.py settings.py models.py(扩展) Dockerfile docker-compose.yml`
- 产出：DeepSeekLlmClient、PromptBuilder、AnswerGenerator、CitationValidator、RefusalPolicy、service 编排（依赖注入 R1 接口，开发期用 fake 实现 mock）、API 扩展、Docker 部署。
- 对外承诺：`/answer` 接 LLM 带引用可拒答；Docker Compose 可起。

### R3 质量 + 集成
- 目录：`trace/ eval/ tests/ rag-mcp-server/ eval/`
- 产出：TraceRecorder、EvalRunner+报告、30 条 eval case、bad case、MCP 对齐新字段、端到端测试。
- 对外承诺：`/eval/run` 真跑；MCP 三工具可用；trace 字段齐全。

### 并发与合并策略
1. Phase 0（本文件）单 worktree 串行冻结契约。
2. 实施：`git-worktree-multi-task` 在 develop 上开 `task/r1-index-retrieval`、`task/r2-gen-service`、`task/r3-quality-mcp` 三目录并发。
3. 合并顺序：**R1 → R2 → R3**（依赖方向）。冲突由 Claude 处理。
4. 合并后跑端到端 smoke（index → search → answer → eval）验收。

---

## 11. 安全边界（冻结）

- 不索引 `.git/.vibe/.vkf/target/node_modules`、密钥/`.env`/生产配置。
- 敏感词问题（密码/密钥/token/cookie/secret）直接拒答。
- 答案必带引用，引用经 `CitationValidator` 校验真实存在于上下文。
- 无证据 / 低分拒答，不强答。
- 所有请求落 trace，可审计。
- MCP 只读，不返回非知识源的本地路径与凭据。

---

## 12. 验收标准（Phase 1~3 完成时）

- [ ] `/index/rebuild` 对 4 个知识源完成加载→切块→embedding→入库，返回真实 doc/chunk 数。
- [ ] `/search?mode=hybrid` 同问题换表达，向量分支比纯关键词更稳；返回 keyword/vector/rerank 分。
- [ ] `/answer` 基于 DeepSeek 生成带引用答案；敏感/无证据问题拒答。
- [ ] `/eval/run` 跑 ≥30 条 case，输出 retrieval_hit / answer_correct / citation_correct / refusal_correct 报告；≥5 个 bad case 有归因。
- [ ] trace 可查，字段含候选/rerank/最终上下文/prompt 版本/model/tokens。
- [ ] MCP `doc.search` / `rag.answer` / `rag.eval.run` 经 HTTP 调通。
- [ ] `docker compose up` 在 2G 机器起服务，curl 可访问。
- [ ] 关键模块有中文注释 + 面试口径 + Java 原型对照说明。

---

## 13. 阶段路线图

```text
Phase 0  本详设（契约冻结）                         ← 当前
Phase 1  R1 索引+检索：embedding/vector/hybrid/rerank
Phase 2  R2 生成+服务：DeepSeek/prompt/引用/拒答/API/Docker
Phase 3  R3 质量+集成：eval/trace/bad case/MCP/部署上线
（Phase 后期可选）QueryRewriter、pgvector 升级、parent-child chunk
```

每个 Phase 用 superpowers：`writing-plans` 出该阶段实施计划 → `git-worktree-multi-task` 并发实施 → 合并 → 验收。
