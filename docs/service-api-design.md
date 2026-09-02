# RAG 服务 API 设计

基础路径：`/api/v1`

## 1. API 总览

正式 RAG 服务对外提供以下能力：

```text
POST /api/v1/index/rebuild       重建索引
POST /api/v1/search              检索相关 chunk
POST /api/v1/answer              基于检索结果生成答案
GET  /api/v1/traces/{trace_id}   查询 trace
POST /api/v1/eval/run            执行 eval
GET  /health                     健康检查
```

当前 `rag-service-python` 处于骨架阶段：

- `search` 和 `answer` 已有基础实现。
- 当前读取 `prototype-cli/data/index/chunks.jsonl`。
- 当前使用关键词检索。
- `index/rebuild` 和 `eval/run` 目前只保留接口形态，后续补实现。

## 2. 重建索引

```http
POST /api/v1/index/rebuild
```

请求示例：

```json
{
  "source_names": ["dubbo", "ddd", "state-machine", "bff"],
  "mode": "full"
}
```

响应示例：

```json
{
  "job_id": "idx_20260615_001",
  "status": "completed",
  "document_count": 112,
  "chunk_count": 1179,
  "started_at": "2026-06-15T10:00:00Z",
  "finished_at": "2026-06-15T10:00:10Z"
}
```

设计意图：

- 生产环境中，索引构建应该和在线问答解耦。
- 后续可以支持全量重建、增量更新、定时任务、Git 文档变更触发。
- 当前 Day1.5 版本暂时读取 Java 原型生成的 JSONL 索引。

## 3. 检索接口

```http
POST /api/v1/search
```

请求示例：

```json
{
  "query": "Dubbo 服务异常应该如何封装？",
  "top_k": 5,
  "filters": {
    "source_name": "dubbo",
    "doc_type": "deep_dive"
  },
  "include_content": true
}
```

响应示例：

```json
{
  "trace_id": "trace_20260615_001",
  "query": "Dubbo 服务异常应该如何封装？",
  "results": [
    {
      "chunk_id": "dubbo_xxx",
      "score": 102.0,
      "source_name": "dubbo",
      "source_path": "04-服务暴露/服务暴露-Dubbo服务设计与异常封装.md",
      "section_path": "Dubbo 服务设计与异常封装 > 7. 结论",
      "doc_type": "knowledge",
      "matched_terms": ["Dubbo", "服务", "异常", "封装"],
      "content": "..."
    }
  ],
  "latency_ms": 30
}
```

字段说明：

| 字段 | 含义 |
|---|---|
| `trace_id` | 本次请求追踪 ID |
| `score` | 检索分数 |
| `source_name` | 知识源，比如 `dubbo`、`ddd` |
| `source_path` | 文档相对路径 |
| `section_path` | Markdown 标题路径 |
| `doc_type` | 文档类型 |
| `matched_terms` | 命中的关键词 |
| `content` | chunk 内容 |

## 4. 问答接口

```http
POST /api/v1/answer
```

请求示例：

```json
{
  "question": "聚合根为什么要保证一致性边界？",
  "top_k": 5,
  "filters": {},
  "require_citation": true,
  "allow_refusal": true
}
```

响应示例：

```json
{
  "trace_id": "trace_20260615_002",
  "question": "聚合根为什么要保证一致性边界？",
  "refused": false,
  "answer": "根据当前知识库...",
  "citations": [
    {
      "chunk_id": "ddd_xxx",
      "source_name": "ddd",
      "source_path": "docs/DDD核心概念理解.md",
      "section_path": "问题4:聚合根如何保证一致性?"
    }
  ],
  "latency_ms": 60
}
```

设计意图：

- `search` 返回证据。
- `answer` 返回基于证据的答案。
- 当前阶段答案是模板化回答。
- 后续 Day3 接入 LLM 后，答案必须继续带引用，并支持无证据拒答。

## 5. Trace 查询接口

```http
GET /api/v1/traces/{trace_id}
```

返回内容包括：

- 原始请求。
- 检索结果。
- 最终上下文。
- 是否拒答。
- 答案元数据。
- latency。
- 后续 LLM token 使用情况。

Trace 的作用：

- 排查为什么答错。
- 判断是 retrieval 失败还是 generation 失败。
- 记录成本、耗时、命中来源和拒答原因。

## 6. Eval 执行接口

```http
POST /api/v1/eval/run
```

请求示例：

```json
{
  "case_set": "day1",
  "top_k": 5
}
```

响应示例：

```json
{
  "report_id": "eval_20260615_001",
  "total": 10,
  "passed": 10,
  "failed": 0,
  "pass_rate": 1.0
}
```

当前状态：

- Java 原型已有 eval。
- Python 服务当前只保留 eval API 形态。
- 后续会把 eval runner 提升到正式服务中。

## 7. API 学习顺序

建议按这个顺序理解：

1. 先看 `POST /api/v1/search`，这是 RAG 的检索核心。
2. 再看 `POST /api/v1/answer`，这是检索增强生成的入口。
3. 再看 `GET /api/v1/traces/{trace_id}`，理解可观测性。
4. 再看 `POST /api/v1/index/rebuild`，理解索引构建和在线查询解耦。
5. 最后看 `POST /api/v1/eval/run`，理解质量评估。
