# Phase 1 · 切块 LLD（Markdown + Parent-Child）

> 类型：详细设计（Low-Level Design），开发者/子 agent 可直接照此实现。
> 范围：仅 Markdown。代码切块（tree-sitter）见 Phase 2，不在本文件。
> 上游契约：`docs/中级RAG-开发详设.md` §4.1 / §5.6；本文件细化到伪代码。
> 目录：`rag-service-python/app/ingestion/`、`app/schema.py`。

---

## 1. 目标与不变量

把一篇 Markdown 文档，转成**可检索（child）+ 可回答（parent）+ 可引用 + 可回溯 + 可增量更新**的知识单元。

必须满足的不变量（测试会逐条验证）：

```text
INV-1  内容完整：除清洗删除外，原文每段都映射到至少一个 child；child 去掉 overlap 后无重复无遗漏。
INV-2  顺序一致：chunk 在文档内顺序 == 原文顺序。
INV-3  大小受控：每个 child token <= child_max；parent token <= parent_max 或被标记为不可拆原子块。
INV-4  结构不破坏：代码围栏成对、表格表头随子表、列表项不腰斩。
INV-5  不跨 Section 合并正文。
INV-6  ID 稳定：同输入+同 chunker_version → chunk_id 完全一致；文档局部改动不引起无关 chunk 的 ID 漂移。
INV-7  可定位：每个 chunk 能用 (start_offset,end_offset) 或 (start_line,end_line) 回到原文。
INV-8  父子一致：每个 child.parent_chunk_id 指向存在的 parent；parent 覆盖其所有 child。
```

---

## 2. 输入 / 输出契约

```python
# 输入
@dataclass
class RawDocument:
    doc_id: str          # 见 §6.1 稳定 doc_id
    source_name: str     # 知识源：dubbo/ddd/state-machine/bff
    source_root: str
    source_path: str     # 相对路径
    file_name: str
    text: str            # 原始 Markdown 全文（已统一为 LF）
    updated_at: str
    content_hash: str    # 文档级 sha256（增量用，见存储 LLD）

# 输出
chunks: list[Chunk]      # 含 parent 与 child 两类，见 §3
```

`ingest` 顶层签名：

```python
class MarkdownChunker:
    def __init__(self, cfg: ChunkConfig, token_counter: TokenCounter): ...
    def split(self, doc: RawDocument) -> list[Chunk]: ...
```

---

## 3. Chunk 数据结构（扩展 详设 §4.1）

`app/schema.py`：

```python
@dataclass(frozen=True)
class Chunk:
    # —— 身份 ——
    chunk_id: str
    doc_id: str
    parent_chunk_id: str | None     # child 指向 parent；parent 为 None
    kind: str                       # "parent" | "child"
    section_id: str                 # 章节稳定 id（同 doc 内）
    chunk_index: int                # 文档内顺序号（展示/排序用，不参与 ID）

    # —— 溯源/定位 ——
    source_name: str
    source_root: str
    source_path: str
    file_name: str
    section_path: str               # "Dubbo 治理 > 超时"
    heading_path: list[str]         # ["Dubbo 治理","超时"]
    start_offset: int               # 原文字符偏移
    end_offset: int
    start_line: int
    end_line: int

    # —— 内容 ——
    content: str
    content_type: str               # paragraph|code|table|list|faq|mixed|heading
    content_length: int             # 字符数
    token_count: int                # 见 §7
    content_hash: str               # chunk 级 sha256（增量去重，见存储 LLD）

    # —— 业务 metadata ——
    title: str = ""
    doc_type: str = ""
    project: str = ""
    version: str = "v1"
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)

    # —— 邻接（上下文扩展用，child 间）——
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None

    # —— 版本 ——
    chunker_version: str = "md-v1"
```

> 只有 **child 进向量索引和 FTS5**；parent 只存元数据库，命中 child 后按 `parent_chunk_id` 取出做上下文扩展。

---

## 4. 处理流水线（总览）

```text
RawDocument.text (LF 归一)
  │
  ① AST 解析   markdown-it-py / mistune → token 流（带行号）
  │
  ② 结构树构建 按 heading 层级建 Section 树；正文挂到所属 Section
  │
  ③ 原子块识别 code/table/list 标记为 atomic，记录 start/end line/offset
  │
  ④ Section → Parent  每个叶子 Section 聚合为 1 个 parent；超 parent_max 则按原子块边界拆成多 parent
  │
  ⑤ Parent → Child   parent 内按原子块/段落/句子递归切，token<=child_max，相邻 overlap
  │
  ⑥ 短块合并   同 Section、结构兼容、合并后不超预算才合并（INV-5）
  │
  ⑦ metadata + 稳定 ID + 邻接指针 + content_hash + token_count
  │
  └→ list[Chunk]（parent 在前或交错，按 chunk_index 定序）
```

---

## 5. 关键步骤伪代码

### 5.1 ② 结构树构建

```python
def build_sections(tokens) -> list[Section]:
    # Section = {heading_path, level, nodes:[Node], start_line, end_line}
    stack = []            # 维护 heading 层级
    sections = []
    heading_path = []
    cur = new_section(heading_path=[])   # 文档开头无标题正文归入根 Section
    for tok in tokens:
        if tok.type == "heading_open":
            flush(cur, sections)
            level = heading_level(tok)          # h1..h6
            text = next_inline_text(tokens)
            heading_path = heading_path[:level-1] + [text]   # 维护层级路径
            cur = new_section(heading_path=list(heading_path), level=level,
                              start_line=tok.map[0])
            # 标题原文也写入 content（检索可见，见 chunking-design §4.1 适度冗余）
            cur.nodes.append(HeadingNode(text, line=tok.map[0]))
        else:
            cur.nodes.append(to_node(tok))      # paragraph/code/table/list...
    flush(cur, sections)
    return sections
```

要点：
- `heading_path` 用切片维护，**自动处理 H2 切换清掉旧 H3**（修正现有 Java 的污染问题）。
- 跳级标题（H1→H3）：路径按出现层级填，缺级不补空（记录到测试 B04 对齐）。
- **代码块里的 `# comment` 不能当标题**——AST 解析天然规避（围栏内是 code token，不是 heading）。

### 5.2 ③ 原子块识别

```python
ATOMIC = {"code", "table"}      # 列表整体尽量原子，超大列表按整项切
def mark_atomic(section):
    for node in section.nodes:
        node.atomic = node.type in ATOMIC
        node.start_offset, node.end_offset = offsets_from_lines(node.map)
```

原子块规则（INV-4）：
- `code`：保留围栏与语言标签；超 `child_max` 时按空行/语句块切，**绝不在 token 中间切**，每片补回围栏。
- `table`：表头随每个子表重复；按数据行分组，组内不腰斩。
- `list`：尽量整列表一个 child；超预算按"整项"为最小单位切，保留列表标题。

### 5.3 ④ Section → Parent

```python
def to_parents(section) -> list[ParentDraft]:
    budget = cfg.parent_max_tokens
    parents, buf, buf_tok = [], [], 0
    for node in section.nodes:
        ntok = token_count(node.text)
        if node.atomic and ntok > budget:
            # 不可拆原子块超预算：单独成 parent 并标记 oversize_atomic
            if buf: parents.append(make_parent(section, buf)); buf, buf_tok = [], 0
            parents.append(make_parent(section, [node], oversize_atomic=True))
            continue
        if buf_tok + ntok > budget and buf:
            parents.append(make_parent(section, buf)); buf, buf_tok = [], 0
        buf.append(node); buf_tok += ntok
    if buf: parents.append(make_parent(section, buf))
    return parents
```

### 5.4 ⑤ Parent → Child（核心）

```python
def to_children(parent) -> list[ChildDraft]:
    units = atomic_aware_units(parent)   # 段落/句子/原子块为最小单位，保持顺序
    children, buf, buf_tok = [], [], 0
    for u in units:
        utok = token_count(u.text)
        if u.atomic and utok > cfg.child_max_tokens:
            if buf: children.append(make_child(buf)); buf, buf_tok = [], 0
            children.append(make_child([u], atomic=True))   # 原子块独占 child
            continue
        if buf_tok + utok > cfg.child_max_tokens and buf:
            children.append(make_child(buf))
            buf, buf_tok = carry_overlap(buf, cfg.child_overlap_tokens)  # 见 §5.5
        buf.append(u); buf_tok += utok
    if buf: children.append(make_child(buf))
    return children
```

### 5.5 overlap 实现（INV-1 去重前提）

```python
def carry_overlap(buf, overlap_tokens):
    # 从已闭合 child 末尾，回带最多 overlap_tokens 的完整句子作为下一个 child 开头
    tail, tok = [], 0
    for u in reversed(buf):
        if tok + token_count(u.text) > overlap_tokens: break
        tail.insert(0, u); tok += token_count(u.text)
    return tail, tok        # 这部分会与上一 child 重叠；重建原文校验时按设计扣除
```

> overlap 只在**非原子、句子边界**回带；原子块不参与 overlap。

### 5.6 ⑥ 短块合并不变量（修正现有跨 Section bug）

```python
def merge_short(children, cfg) -> list:
    out = []
    for c in children:
        if (out and c.token_count < cfg.child_min_tokens
                and same_section(out[-1], c)                 # ★ 同 Section
                and structure_compatible(out[-1], c)         # 非两个原子块强并
                and out[-1].token_count + c.token_count <= cfg.child_max_tokens):
            out[-1] = recombine(out[-1], c)                  # 合并后重算 token/offset/hash
        else:
            out.append(c)
    return out
```

对照现有 Java 的 4 个缺陷，本实现修正：①不跨 Section（INV-5）②合并后重算并校验上限（INV-3）③原子块不被并坏（INV-4）④标题不会被动成孤块（标题随 Section 进入父子结构）。

---

## 6. 稳定 ID（INV-6，解决"全量重生成"根因）

### 6.1 doc_id

```python
doc_id = "d_" + sha1(f"{source_name}:{source_path}")[:12]   # 路径稳定，不含内容
```

### 6.2 section_id / chunk_id

```python
section_id = "s_" + sha1(f"{doc_id}:{'>'.join(heading_path)}")[:12]
# child/parent 内容哈希参与 ID → 内容不变则 ID 不变；插入段落只影响被改 chunk
content_hash = sha256(normalized(content))                  # normalized: strip+collapse空白
chunk_id = f"{kind[0]}_" + sha1(f"{section_id}:{content_hash}")[:16]
```

> 关键效果：文档开头插一段，**只有受影响 child 的 ID 变**，其余 child 的 `chunk_id` 不变 → 增量索引可跳过未变 chunk、复用已生成向量（详见存储 LLD 增量算法）。

---

## 7. token 计数（启发式起步，可插拔）

```python
class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

class HeuristicTokenCounter:
    # 标定：CJK ≈ 字数×0.7；ASCII 词 ≈ len/4；混合分别算后相加
    def count(self, text: str) -> int:
        cjk = sum(1 for ch in text if '一' <= ch <= '鿿')
        ascii_chars = sum(1 for ch in text if ch.isascii())
        return round(cjk * 0.7) + round(ascii_chars / 4) + 0
```

> 决策⑷：启发式起步。若 eval 显示 child 实际 token 与预算偏差 >15%，再换 `BgeM3TokenCounter`（transformers 真 tokenizer，仅索引期离线用）。接口不变。

---

## 8. 配置项

```python
class ChunkConfig(BaseModel):
    parent_max_tokens: int = 1200
    child_max_tokens: int = 500
    child_min_tokens: int = 120
    child_overlap_tokens: int = 80
    chunker_version: str = "md-v1"
    exclude_globs: list[str] = [".git/**","**/target/**","**/node_modules/**",
                                ".vibe/**",".vkf/**","**/*.toon"]
```

初始值是实验起点，最终由 §10 eval 调（不是拍脑袋）。

---

## 9. 边界用例（必须有断言）

| 编号 | 输入 | 期望 |
|---|---|---|
| C01 | 无标题短文档 | 1 个 section（根），≥1 child；section_path = 文件名去扩展 |
| C02 | H1/H2/H3 | heading_path 正确；H2 切换清掉旧 H3 |
| C03 | 跳级 H1→H3 | 路径按出现层级，不补空级 |
| C04 | Section 恰好 = parent_max | 不拆 parent |
| C05 | 单段 > child_max | 句子边界切，非字符硬切 |
| C06 | 代码块 > child_max | 按语句块切，每片含围栏与语言标签 |
| C07 | 表格跨多 child | 每片含表头 |
| C08 | 同 Section 尾块 < min | 向同 Section 前块合并，重算上限 |
| C09 | 新 Section 短块 | **不**跨 Section 合并（对照旧 bug） |
| C10 | 文档开头插一段 | 仅受影响 child 的 chunk_id 变，其余不变（INV-6 回归） |
| C11 | CRLF / emoji / 连续空行 | 不损坏内容，不抛异常 |
| C12 | 未闭合代码围栏 | 容错处理，不吞后续内容 |

---

## 10. 测试清单（分层，对齐 chunking-design.md §12）

```text
L1 不变量单测      INV-1..INV-8 各 1+ 用例
L2 边界用例        C01..C12
L3 属性测试        随机标题/长度/Unicode → 不抛异常 / 至少1 child / 重建正文一致(扣overlap) /
                  child token<=max / 不跨 section / 同输入两次结果全等
L4 Golden File     10~20 个真实/脱敏 md，固定期望 chunks.json；改参数时看 diff
L5 检索 eval       见 retrieval/eval LLD：Recall@K / Boundary Failure Rate
```

P0（实现切块时必须先有）：INV-1/2/5/6 + C09/C10。

---

## 11. 代码 RAG 扩展点（Phase 2 预留，本期不实现）

- `Chunk.content_type` 已含 `code`；Phase 2 加 `language/package/class_name/method_name`。
- chunker 按 `source.kind` 分发：`MarkdownChunker` | `CodeChunker(tree-sitter)`，共用本文件的 parent-child、稳定 ID、token、合并不变量框架。
- 代码的"Section"= 文件/类，"原子块"= 方法/函数；ID 用 `git_blob_hash` 增强稳定性。
