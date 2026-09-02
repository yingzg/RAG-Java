# Phase 1 · 存储与增量索引 LLD（SQLite + FTS5 + 向量 + Hash 变更检测）

> 类型：详细设计（LLD），开发者/子 agent 可直接照此实现。
> 范围：Markdown 知识源的持久化存储、增量索引、BM25 与向量底座。
> 上游契约：`docs/中级RAG-开发详设.md` §4 / §5.2 / §5.3 / §5.6；切块见 `Phase1-切块-LLD.md`。
> 目录：`rag-service-python/app/store/`、`app/ingestion/index_service.py`、`app/embedding/`。

---

## 1. 目标（解决"玩具 JSON + 全量重生成"）

```text
G1  持久化用 SQLite，不用裸 JSONL：支持事务、增量 upsert/delete、metadata 结构化查询。
G2  BM25 用 SQLite FTS5（真倒排索引 + bm25() 排序），中文 jieba 预分词。
G3  向量用本地文件（numpy）起步；接口抽象，Phase 2 可换 sqlite-vec/faiss/量化。
G4  增量索引：基于 hash 的变更检测，只处理新增/修改/删除的文档；
    chunk 级 hash 去重 → 内容未变的 chunk 复用旧向量，不重复调 embedding API（省钱省时）。
G5  一致性：一次 rebuild 在事务内完成，失败可回滚，不留半截索引。
```

---

## 2. 存储总体布局

```text
data/index/
├─ rag.db                # SQLite：documents / chunks / chunks_fts(FTS5) / vectors_meta / index_meta
├─ vectors.npy           # float32 [N,1024] 向量矩阵（child 向量）
└─ vectors_ids.json      # 行号 → chunk_id 映射（与 vectors.npy 对齐）
```

> 为什么向量不进 SQLite BLOB（Phase 1）：numpy 矩阵做 brute-force cosine 最简单最快。Phase 2 数据变大再换 sqlite-vec（届时向量进 db.rag）。`VectorStore` 接口隔离了这个选择。

---

## 3. 数据库 DDL

```sql
-- 文档级（增量变更检测的锚点）
CREATE TABLE documents (
  doc_id        TEXT PRIMARY KEY,
  source_name   TEXT NOT NULL,
  source_path   TEXT NOT NULL,
  file_name     TEXT,
  title         TEXT,
  doc_type      TEXT,
  version       TEXT DEFAULT 'v1',
  content_hash  TEXT NOT NULL,         -- 文档级 sha256
  updated_at    TEXT,
  indexed_at    TEXT,
  chunk_count   INTEGER DEFAULT 0
);
CREATE INDEX idx_documents_source ON documents(source_name);

-- chunk 级（parent + child 都存）
CREATE TABLE chunks (
  chunk_id        TEXT PRIMARY KEY,
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  parent_chunk_id TEXT,
  kind            TEXT NOT NULL,        -- parent|child
  section_id      TEXT,
  chunk_index     INTEGER,
  source_name     TEXT, source_path TEXT, file_name TEXT,
  section_path    TEXT, heading_path TEXT,        -- heading_path 存 JSON 字符串
  content_type    TEXT,
  content         TEXT NOT NULL,
  content_length  INTEGER, token_count INTEGER,
  content_hash    TEXT NOT NULL,        -- chunk 级 sha256（去重/复用向量）
  start_offset INTEGER, end_offset INTEGER, start_line INTEGER, end_line INTEGER,
  prev_chunk_id   TEXT, next_chunk_id TEXT,
  project TEXT, version TEXT DEFAULT 'v1', updated_at TEXT,
  tags            TEXT,                 -- JSON 数组字符串
  chunker_version TEXT,
  has_vector      INTEGER DEFAULT 0     -- child 是否已生成向量
);
CREATE INDEX idx_chunks_doc   ON chunks(doc_id);
CREATE INDEX idx_chunks_kind  ON chunks(kind);
CREATE INDEX idx_chunks_chash ON chunks(content_hash);
CREATE INDEX idx_chunks_meta  ON chunks(source_name, doc_type, project, version);

-- FTS5：仅 child 入，BM25 关键词检索；content 已 jieba 预分词（空格分隔）
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  chunk_id UNINDEXED,
  title,                  -- jieba 分词后的标题
  section_path,           -- jieba 分词后的章节路径
  content,                -- jieba 分词后的正文
  tokenize = 'unicode61'  -- 已预分词，故用 unicode61 按空格切
);

-- 索引元信息
CREATE TABLE index_meta (
  key TEXT PRIMARY KEY, value TEXT
);  -- embedding_model, embedding_dim, chunker_version, last_rebuild_at ...
```

> `chunks_fts` 与 `chunks` 用 `chunk_id` 关联（不用 FTS5 外部内容表，降低同步复杂度；写入时两边一起改，包在同一事务）。

---

## 4. 抽象接口（实现 详设 §5.2 / §5.3）

```python
class ChunkStore(Protocol):
    def upsert_document(self, doc: DocumentRow) -> None: ...
    def get_document(self, doc_id: str) -> DocumentRow | None: ...
    def list_documents(self, source_name: str | None = None) -> list[DocumentRow]: ...
    def delete_document(self, doc_id: str) -> None: ...        # 级联删 chunks + fts
    def upsert_chunks(self, chunks: list[Chunk]) -> None: ...  # 同步写 chunks + chunks_fts
    def delete_chunks_of_doc(self, doc_id: str) -> None: ...
    def get_chunk(self, chunk_id: str) -> Chunk | None: ...
    def get_children_content_hashes(self, doc_id: str) -> dict[str, str]: ...  # chunk_id->hash
    def get_parent(self, parent_chunk_id: str) -> Chunk | None: ...
    def bm25_search(self, query_tokens: str, top_k: int, filters: dict) -> list[Bm25Hit]: ...

class VectorStore(Protocol):                  # 详设 §5.2
    def upsert(self, items: list[VectorItem]) -> None: ...
    def search(self, q: list[float], top_k: int, filters: dict | None) -> list[VectorHit]: ...
    def delete(self, chunk_ids: list[str]) -> None: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...
```

---

## 5. FTS5 + jieba（决策⑵ 落地）

写入：

```python
def fts_text(s: str) -> str:
    return " ".join(jieba.cut_for_search(s))   # 预分词，空格连接

# upsert_chunks 内，仅 child：
INSERT INTO chunks_fts(chunk_id, title, section_path, content)
VALUES (?, ?, ?, ?)              # 三个文本字段都过 fts_text()
```

查询（BM25，列权重对应 详设 §6 的 field boost）：

```sql
SELECT chunk_id,
       bm25(chunks_fts, 0.0, 5.0, 3.0, 1.0) AS score   -- 列权重: id0, title5, section3, content1
FROM chunks_fts
WHERE chunks_fts MATCH :q                                -- :q = fts_text(query)
ORDER BY score                                           -- bm25() 越小越相关
LIMIT :top_k;
```

> metadata filter（source_name/doc_type/project/version）在 `chunks` 表上做，与 FTS 结果按 chunk_id JOIN。这对应 详设 §5 的"结构化过滤 + 正文相关性"分离。

---

## 6. 向量存储（numpy 实现，决策⑶）

```python
class LocalVectorStore:                # implements VectorStore
    # 内存持有 matrix:[N,1024] float32 + ids:list[str] + id2row:dict
    def upsert(self, items):
        for it in items:
            if it.chunk_id in self.id2row: self.matrix[self.id2row[it.chunk_id]] = it.embedding
            else: append_row(it.chunk_id, it.embedding)
        self._dirty = True
    def search(self, q, top_k, filters=None):
        # 预归一化 → cosine = 点积
        sims = self.matrix @ normalize(q)            # [N]
        idx = np.argpartition(-sims, top_k)[:top_k]
        return [VectorHit(self.ids[i], float(sims[i])) for i in sorted(idx, key=lambda i:-sims[i])]
    def delete(self, chunk_ids): mark rows, compact on flush
    def flush(self): np.save(vectors.npy, matrix); write vectors_ids.json
```

要点：写入时即归一化，search 用矩阵乘；`filters` 在 Phase 1 由上层先用 SQLite 缩小候选 chunk_id 集合再传入（小数据可后过滤）。Phase 2 换 sqlite-vec 时本类整体替换。

---

## 7. 增量索引算法（G4，核心，详设漏掉的部分）

`IndexService.rebuild(source_names, mode)`：

```python
def rebuild(source_names, mode="incremental"):
    with db.transaction():                       # G5 一致性
        scanned = scan_sources(source_names)     # 读 .md → RawDocument(含 doc 级 content_hash)
        existing = {d.doc_id: d for d in store.list_documents(source_names)}
        scanned_ids = {d.doc_id for d in scanned}
        stats = Stats()

        # —— 删除：库里有、扫描没有 ——
        for doc_id in existing.keys() - scanned_ids:
            store.delete_document(doc_id)         # 级联删 chunks + fts
            vector_store.delete(children_of(doc_id))
            stats.deleted += 1

        for doc in scanned:
            old = existing.get(doc.doc_id)
            # —— 未变：doc 级 hash 相同 → 跳过 ——
            if old and old.content_hash == doc.content_hash and mode != "full":
                stats.skipped += 1; continue

            # —— 新增 或 修改 ——
            new_chunks = chunker.split(doc)               # 切块（含稳定 chunk_id + content_hash）
            new_children = [c for c in new_chunks if c.kind == "child"]

            # ★ chunk 级 hash 去重：复用未变 child 的向量，只对新/变 child 调 embedding
            old_hashes = store.get_children_content_hashes(doc.doc_id) if old else {}
            reuse, to_embed = [], []
            old_hash2id = {h: cid for cid, h in old_hashes.items()}
            for c in new_children:
                if c.content_hash in old_hash2id and chunk_id_unchanged(c, old_hash2id):
                    reuse.append(c)                       # 向量已存在，迁移 has_vector
                else:
                    to_embed.append(c)

            # 替换该 doc 的所有 chunk（先删后插，保证干净）
            if old:
                store.delete_chunks_of_doc(doc.doc_id)
                vector_store.delete(list(old_hashes.keys()))   # 旧向量删，下面按需重建
            store.upsert_document(to_doc_row(doc))
            store.upsert_chunks(new_chunks)                    # 同步写 chunks + chunks_fts

            # 仅对 to_embed 调 embedding API（批量，§8）
            if to_embed:
                vecs = embedder.embed_documents([c.content for c in to_embed])
                vector_store.upsert([VectorItem(c.chunk_id, v, meta(c))
                                     for c, v in zip(to_embed, vecs)])
            # 复用向量：重新写回（因上面整体删了该 doc 旧向量，reuse 也需重嵌或保留缓存）
            #   实现选择 A(简单)：reuse 也重新 embedding（仍省在"未改文档整篇跳过"）
            #   实现选择 B(省钱)：embedding 另建 content_hash->vector 持久缓存表，命中即取
            stats.new_or_updated += 1
            stats.embedded_chunks += len(to_embed)

        vector_store.flush()
        store.set_meta(last_rebuild_at=now(), embedding_model=cfg.embedding_model)
    return IndexRebuildResponse(..., **stats.as_counts())
```

### 7.1 两级去重的收益层次

```text
第1级（文档级 hash）：未改的文档整篇跳过 → 200 篇里改 3 篇，只处理 3 篇。
第2级（chunk 级 hash）：改动的文档里，只有被动到的 child 重新 embedding。
                       配合 §7.2 的 embedding 缓存表，可做到"全库改 1 段只调 1 次 API"。
```

### 7.2 embedding 缓存表（实现选择 B，推荐）

```sql
CREATE TABLE embedding_cache (
  content_hash TEXT PRIMARY KEY,    -- = chunk.content_hash
  model        TEXT NOT NULL,
  dim          INTEGER,
  vector       BLOB NOT NULL,       -- float32 bytes
  created_at   TEXT
);
```

`embed_documents` 前先查缓存：命中 `content_hash`(+同 model) 直接取向量，未命中才调 API 并回写。换 embedding 模型时 `model` 不同 → 自动失效重算（对应学习计划"换模型需重建索引"）。

> 决策：Phase 1 先实现"选择 A（文档级跳过）"保证简单可用；`embedding_cache` 作为 §7.2 增强项紧随其后（低风险、高收益）。

---

## 8. Embedding 调用（详设 §5.1 实现要点）

```python
class SiliconFlowEmbeddingClient:
    model = "BAAI/bge-m3"; dimension = 1024
    def embed_documents(self, texts):
        out = []
        for batch in chunked(texts, size=32):        # 分批 ≤32
            out += retry(lambda: post(f"{base}/embeddings",
                          json={"model": self.model, "input": batch}).data)
        return [normalize(v) for v in out]           # 存归一化向量，cosine=点积
    def embed_query(self, text): return normalize(post(... input=[text]).data[0])
```

- 重试：429/5xx 指数退避，最多 3 次。
- 速率保护：批间小 sleep，避免触发限流。
- 失败传播：整批失败则该文档本次索引失败、回滚（事务），不写半截。

---

## 9. 一致性与边界

```text
B-1  rebuild 全程单事务；中途异常 → 回滚，索引保持上一次完好状态。
B-2  chunks 与 chunks_fts 必须同写同删（同事务），否则 BM25 与元数据漂移。
B-3  vectors.npy 在事务提交后 flush；若 flush 失败，记录 dirty 标志，下次启动校验 has_vector 与向量行数一致性。
B-4  doc_id 基于 source_path：文件改名 = 删旧 doc + 新增 doc（可接受；Phase 2 代码源可用 git rename 检测优化）。
B-5  embedding_dim 写入 index_meta；启动时与配置比对，不一致则要求 full rebuild（防换模型后维度混用）。
```

---

## 10. 测试清单

```text
T1 DDL/迁移      建库、索引存在、外键级联删生效
T2 ChunkStore    upsert/get/delete；chunks 与 chunks_fts 同步；filters 查询正确
T3 FTS5/BM25     jieba 预分词写入；MATCH 命中；列权重生效；中文/符号(类名)均可召回
T4 VectorStore   upsert/search/delete；cosine 排序正确；归一化后点积==cosine
T5 增量-未变     改 0 篇 rebuild → skipped==全部，embedded_chunks==0
T6 增量-新增     加 1 篇 → new==1，其余 skipped
T7 增量-修改     改 1 篇里 1 段 → 该 doc 重切；(选择B)embedded_chunks 仅=变动 child 数
T8 增量-删除     删 1 篇文件 → documents/chunks/fts/vectors 全部清除
T9 缓存命中      embedding_cache：相同 content_hash 不二次调 API（mock 计数）
T10 一致性回滚   embedding 中途抛错 → 事务回滚，库与上次一致
T11 换模型       embedding_model 变更 → 维度校验触发 full rebuild
```

P0：T2/T3/T5/T7/T8（增量正确性是本 LLD 的命脉）。

---

## 11. 配置项（汇入 详设 §8 Settings）

```python
db_path: Path = data_dir/"index"/"rag.db"
vector_path: Path = data_dir/"index"/"vectors.npy"
embedding_batch_size: int = 32
embedding_cache_enabled: bool = True
default_index_mode: str = "incremental"     # incremental | full
```

---

## 12. 代码 RAG 扩展点（Phase 2 预留）

- `documents` 增 `repo_url/branch/commit_sha`；变更检测从"文件 hash"升级为"**git commit/blob hash**"（拉取后 `git diff` 直接给出新增/修改/删除文件，比全量扫描更快）。
- 向量规模上来后：`LocalVectorStore` → `SqliteVecVectorStore`（on-disk）或 int8 量化；接口不变。
- `embedding_cache` 对代码同样适用：未改方法不重嵌。
