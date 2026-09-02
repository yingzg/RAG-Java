# RAG-Java 项目快速学习指南

## 1. 先给结论：这个项目目前实现了什么

当前项目不是一个完整生产级 RAG，而是一个分阶段演进的 RAG 学习与生产雏形项目。

它目前包含三部分：

```text
prototype-cli       Java CLI 原型，已经实现 Day1 RAG 最小闭环
rag-service-python  Python FastAPI 正式服务骨架，已实现基础 search/answer API
rag-mcp-server      TypeScript MCP 适配层骨架，已定义 doc.search / rag.answer / rag.eval.run
```

当前已经真正跑通的核心能力在 `prototype-cli`：

- 文档源配置。
- Markdown 文档加载。
- 排除 `.git/.vibe/.vkf/target/node_modules` 等无关目录。
- Markdown 标题切块。
- metadata 提取。
- JSONL 本地索引。
- 关键词检索。
- 模板化回答。
- 引用。
- 敏感问题拒答。
- trace 记录。
- eval 简版评估。

当前 `rag-service-python` 是正式 RAG 服务方向的骨架：

- 已提供 FastAPI API。
- 已能读取 `prototype-cli` 的 JSONL chunk。
- 已有 Python 版关键词检索。
- 已有模板化 answer 和拒答。
- 已有 trace 写入。
- 还没有接 embedding、向量库、LLM、rerank。

当前 `rag-mcp-server` 是 MCP 适配层骨架：

- 定义了 `doc.search`。
- 定义了 `rag.answer`。
- 定义了 `rag.eval.run`。
- 通过 HTTP 调用 `rag-service-python`。
- 还没有完成依赖安装和运行验证。

## 2. 当前能力成熟度

| 能力 | 当前状态 | 位置 |
|---|---|---|
| 文档导入 | 已实现 | `prototype-cli` |
| Markdown 切块 | 已实现 | `prototype-cli` |
| metadata | 已实现 | `prototype-cli` |
| 本地索引 | 已实现，JSONL | `prototype-cli/data/index/chunks.jsonl` |
| 关键词检索 | 已实现 | `prototype-cli`、`rag-service-python` |
| 向量检索 | 未实现 | Day2 |
| embedding | 未实现 | Day2 |
| hybrid search | 未实现 | Day3 |
| rerank | 未实现 | Day3 |
| LLM answer | 未实现 | Day3 |
| 模板化 answer | 已实现 | `prototype-cli`、`rag-service-python` |
| 引用 | 已实现基础版 | `prototype-cli`、`rag-service-python` |
| 拒答 | 已实现基础版 | `prototype-cli`、`rag-service-python` |
| trace | 已实现基础版 | `prototype-cli`、`rag-service-python` |
| eval | Java 原型已实现 | `prototype-cli` |
| HTTP API | 已有骨架 | `rag-service-python` |
| MCP Tool | 已有骨架 | `rag-mcp-server` |

## 3. 推荐阅读顺序

你现在看代码没有头绪是正常的，因为项目包含原型、正式服务、MCP 适配三层。不要按文件树从上到下看，按能力链路看。

### 第 1 步：先看总架构文档

先读：

1. `docs/architecture.md`
2. `docs/language-decision.md`
3. `README.md`

目标：

- 理解为什么 RAG 是独立知识服务。
- 理解为什么正式服务选 Python。
- 理解 Java 原型和正式服务的关系。
- 理解 MCP Server 只是薄适配层。

不要急着看源码。

### 第 2 步：先跑 Java 原型

进入：

```bash
cd /mnt/d/个人项目/RAG-Java/prototype-cli
```

运行：

```bash
mvn package
java -jar target/rag-java-0.1.0.jar index
java -jar target/rag-java-0.1.0.jar search "Dubbo 服务异常应该如何封装？" --topK 3
java -jar target/rag-java-0.1.0.jar answer "聚合根为什么要保证一致性边界？"
java -jar target/rag-java-0.1.0.jar answer "生产数据库密码是什么？"
java -jar target/rag-java-0.1.0.jar eval
```

目标：

- 先看到 RAG 最小闭环真的能跑。
- 观察 `search` 返回什么。
- 观察 `answer` 如何带引用。
- 观察敏感问题如何拒答。
- 观察 eval 报告。

### 第 3 步：看 Java 原型入口

先看：

```text
prototype-cli/src/main/java/com/example/rag/RagCliApplication.java
```

这个文件是 Java 原型的总入口。

重点看四个命令：

- `index`
- `search`
- `answer`
- `eval`

对应 RAG 四个学习动作：

```text
index   建索引
search  检索证据
answer  基于证据回答
eval    评估效果
```

你只要先看懂这个文件，项目就有主线了。

### 第 4 步：按 RAG 链路看 Java 原型源码

不要按包名随便看，按这条链路看：

```text
配置知识源
  -> 加载 Markdown
  -> 切 chunk
  -> 写索引
  -> 读取索引
  -> 检索
  -> 回答
  -> trace
  -> eval
```

对应文件顺序：

1. `config/DocumentSource.java`
2. `config/SourceConfigLoader.java`
3. `document/MarkdownLoader.java`
4. `document/MarkdownChunker.java`
5. `document/MetadataExtractor.java`
6. `document/DocumentChunk.java`
7. `index/IndexService.java`
8. `index/JsonlChunkStore.java`
9. `retrieval/QueryTokenizer.java`
10. `retrieval/KeywordRetriever.java`
11. `answer/AnswerBuilder.java`
12. `answer/RefusalPolicy.java`
13. `trace/TraceRecorder.java`
14. `eval/EvalRunner.java`

这就是当前项目最完整的 RAG 学习链路。

### 第 5 步：看 Python 正式服务骨架

先看：

```text
rag-service-python/app/main.py
```

这个文件定义 HTTP API：

- `/health`
- `/api/v1/index/rebuild`
- `/api/v1/search`
- `/api/v1/answer`
- `/api/v1/traces/{trace_id}`
- `/api/v1/eval/run`

然后看：

```text
rag-service-python/app/service.py
```

这是 Python 服务当前的核心协调类：

- 读取 JSONL chunk。
- 调关键词检索。
- 生成模板化 answer。
- 判断是否拒答。
- 写 trace。

再看：

```text
rag-service-python/app/retrieval.py
rag-service-python/app/store.py
rag-service-python/app/models.py
```

目标：

- 理解正式服务如何把 Java 原型里的能力服务化。
- 理解后续 embedding/vector store 应该加在哪里。

### 第 6 步：最后看 MCP 适配层

先看：

```text
rag-mcp-server/src/ragClient.ts
```

它负责调用 Python RAG HTTP API。

再看：

```text
rag-mcp-server/src/index.ts
```

它负责定义 MCP tools：

- `doc.search`
- `rag.answer`
- `rag.eval.run`

你只需要理解：

```text
MCP Server 不做 RAG，只把 RAG 服务暴露给 Agent。
```

## 4. 当前项目的核心知识点

### 4.1 RAG 的两条链路

RAG 要分成两条链路：

```text
离线索引链路：
文档 -> 解析 -> 清洗 -> chunk -> metadata -> embedding -> 索引

在线问答链路：
问题 -> 检索 -> rerank -> 上下文 -> LLM -> 引用 -> 拒答 -> trace
```

当前项目已经实现了离线索引链路的前半段：

```text
Markdown -> chunk -> metadata -> JSONL 索引
```

也实现了在线问答链路的基础版：

```text
问题 -> 关键词检索 -> 模板化回答 -> 引用 -> 拒答 -> trace
```

还没实现：

```text
embedding
向量检索
hybrid search
rerank
LLM answer
```

### 4.2 chunk 是什么

chunk 是把长文档切成适合检索的小片段。

当前项目在 `MarkdownChunker.java` 里实现：

- 按 Markdown 标题切块。
- 保留标题路径 `section_path`。
- 太长的块按段落拆分。

为什么重要：

- chunk 太大，检索噪音多。
- chunk 太小，语义不完整。
- 保留标题路径能让引用更清晰。

### 4.3 metadata 是什么

metadata 是 chunk 的结构化信息。

当前 `DocumentChunk` 包含：

- `chunkId`
- `sourceName`
- `sourceRoot`
- `sourcePath`
- `fileName`
- `sectionPath`
- `chunkIndex`
- `docType`
- `content`
- `contentLength`

metadata 的作用：

- 输出引用。
- 做过滤。
- 做权限。
- 做 trace。
- 做 eval。

### 4.4 retrieval 是什么

retrieval 是根据用户问题找出最相关的 chunk。

当前项目实现的是关键词检索：

```text
query -> token -> score chunk -> topK
```

核心文件：

```text
QueryTokenizer.java
KeywordRetriever.java
```

后续会升级成：

```text
关键词检索 + 向量检索 + metadata filter + rerank
```

### 4.5 answer 是什么

answer 是基于检索结果生成答案。

当前项目不是 LLM answer，而是模板化 answer：

```text
检索结果 -> 摘要 -> 引用
```

核心文件：

```text
AnswerBuilder.java
```

后续 Day3 会升级为：

```text
检索结果 -> prompt -> LLM -> 答案 + 引用
```

### 4.6 refusal 是什么

refusal 是无证据或敏感问题拒答。

当前项目在 `RefusalPolicy.java` 中实现：

- 最高分太低则拒答。
- 命中密码、token、cookie、secret 等敏感词则拒答。

这很重要，因为生产 RAG 不是所有问题都应该回答。

### 4.7 trace 是什么

trace 是一次 RAG 请求的流水账。

当前项目会记录：

- trace id
- 请求类型
- 问题
- topK
- 检索到的 chunks
- 是否拒答
- latency
- created_at

作用：

- 排查为什么答错。
- 判断检索是否命中。
- 分析拒答是否合理。
- 后续统计成本和 token。

### 4.8 eval 是什么

eval 是用固定测试集评估 RAG 效果。

当前 Java 原型中 `EvalRunner.java` 会跑 10 条 case：

- Dubbo 问题
- DDD 问题
- 状态机问题
- BFF 问题
- 敏感拒答问题

当前评估维度较简单：

- 期望知识源是否命中。
- 应拒答的问题是否拒答。

后续要扩展：

- recall@k
- citation_correct
- answer_correct
- refusal_correct
- latency
- hallucination

## 5. 如果只想快速看懂项目，看这 8 个文件

最短路径：

1. `README.md`
2. `docs/architecture.md`
3. `prototype-cli/src/main/java/com/example/rag/RagCliApplication.java`
4. `prototype-cli/src/main/java/com/example/rag/document/MarkdownChunker.java`
5. `prototype-cli/src/main/java/com/example/rag/retrieval/KeywordRetriever.java`
6. `prototype-cli/src/main/java/com/example/rag/answer/AnswerBuilder.java`
7. `rag-service-python/app/main.py`
8. `rag-service-python/app/service.py`

这 8 个文件看完，你就能掌握当前项目 70% 的主线。

## 6. 如果想按能力学习，看这个顺序

### 第一阶段：理解“文档如何变成 chunk”

看：

- `MarkdownLoader.java`
- `MarkdownChunker.java`
- `DocumentChunk.java`

对应 RAG 知识：

- ingestion
- chunk
- metadata

### 第二阶段：理解“chunk 如何被存起来”

看：

- `IndexService.java`
- `JsonlChunkStore.java`
- `data/index/chunks.jsonl`

对应 RAG 知识：

- index
- storage
- offline pipeline

### 第三阶段：理解“问题如何找到 chunk”

看：

- `QueryTokenizer.java`
- `KeywordRetriever.java`

对应 RAG 知识：

- retrieval
- topK
- score
- keyword search

### 第四阶段：理解“检索结果如何变成答案”

看：

- `AnswerBuilder.java`
- `RefusalPolicy.java`

对应 RAG 知识：

- context
- citation
- refusal
- answer generation 前置结构

### 第五阶段：理解“如何追踪和评估”

看：

- `TraceRecorder.java`
- `EvalRunner.java`
- `data/eval/rag_eval_report.md`

对应 RAG 知识：

- trace
- eval
- bad case

### 第六阶段：理解“如何服务化”

看：

- `rag-service-python/app/main.py`
- `rag-service-python/app/service.py`
- `docs/service-api-design.md`

对应 RAG 知识：

- HTTP API
- independent RAG service
- online query service

### 第七阶段：理解“如何给 Agent 使用”

看：

- `rag-mcp-server/src/ragClient.ts`
- `rag-mcp-server/src/index.ts`
- `docs/mcp-tool-design.md`

对应 RAG 知识：

- MCP Tool
- Agent tool use
- RAG as context provider

## 7. 当前项目还缺什么

当前缺少生产 RAG 的关键能力：

1. Embedding。
2. 向量检索。
3. 向量存储。
4. Hybrid search。
5. Rerank。
6. LLM answer。
7. 引用校验。
8. 更完整 eval。
9. bad case 文档。
10. 权限过滤。
11. 增量索引。

这些就是后续学习和开发重点。

## 8. 面试时如何讲当前项目

可以这样讲：

> 我把 RAG 拆成两个阶段学习。第一阶段先用 Java CLI 手写了一个最小 RAG 原型，用来理解文档加载、chunk、metadata、检索、引用、拒答、trace 和 eval。这个原型不是生产入口。第二阶段把架构纠偏为独立 RAG Knowledge Service，用 Python FastAPI 承载正式 RAG 服务，用 TypeScript MCP Server 暴露给 Agent。Java 业务服务只通过 HTTP 调用 RAG，不把 RAG 内部复杂度耦合进业务系统。

再补一句：

> 当前项目已经跑通了无 embedding 的 RAG 最小闭环，后续会加入 embedding、向量库、hybrid search、rerank 和 LLM answer，逐步接近生产级 RAG。

## 9. 你现在最应该做的事

不要一开始追着所有文件看。

建议今天只做三件事：

1. 跑一遍 `prototype-cli` 的 `index/search/answer/eval`。
2. 看懂 `RagCliApplication.java` 的四个命令入口。
3. 看懂 `MarkdownChunker.java` 和 `KeywordRetriever.java`。

这样你就能建立第一层 RAG 直觉：

```text
文档如何变成 chunk；
问题如何找到 chunk；
检索结果如何形成引用和答案；
为什么需要拒答和 trace。
```

完成这一步后，再进入 Day2：embedding 和向量检索。
