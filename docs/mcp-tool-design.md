# MCP Tool 设计

## 1. MCP Server 的定位

`rag-mcp-server` 是 RAG 服务的 TypeScript MCP 适配层。

它是一个很薄的协议适配器：

```text
MCP Client / Agent / IDE
  -> rag-mcp-server
  -> rag-service-python HTTP API
```

它不负责：

- 文档解析。
- chunk。
- embedding。
- 向量库查询。
- rerank。
- LLM 生成。
- eval 计算。

这些能力都属于独立的 RAG 服务。

## 2. Tool：`doc.search`

用途：检索可引用的文档 chunk。

适合场景：

- Agent 需要查 Dubbo 规范。
- Agent 需要查 DDD 概念。
- Agent 需要查状态机文档。
- Agent 需要拿到证据片段，而不是直接生成完整答案。

输入 schema：

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "检索问题"
    },
    "domain": {
      "type": "string",
      "enum": ["dubbo", "ddd", "state-machine", "bff"],
      "description": "可选知识域过滤"
    },
    "doc_type": {
      "type": "string",
      "description": "可选文档类型过滤"
    },
    "top_k": {
      "type": "integer",
      "default": 5
    }
  },
  "required": ["query"]
}
```

映射到 RAG 服务：

```http
POST /api/v1/search
```

## 3. Tool：`rag.answer`

用途：基于检索到的知识生成带引用、可拒答的答案。

适合场景：

- 用户直接问“聚合根为什么要保证一致性边界？”
- Agent 需要给出一个完整解释。
- 面试演示时需要展示“基于证据回答”。

输入 schema：

```json
{
  "type": "object",
  "properties": {
    "question": {
      "type": "string"
    },
    "domain": {
      "type": "string",
      "enum": ["dubbo", "ddd", "state-machine", "bff"]
    },
    "top_k": {
      "type": "integer",
      "default": 5
    },
    "require_citation": {
      "type": "boolean",
      "default": true
    },
    "allow_refusal": {
      "type": "boolean",
      "default": true
    }
  },
  "required": ["question"]
}
```

映射到 RAG 服务：

```http
POST /api/v1/answer
```

## 4. Tool：`rag.eval.run`

用途：运行指定 eval case set，并返回评估摘要。

输入 schema：

```json
{
  "type": "object",
  "properties": {
    "case_set": {
      "type": "string",
      "default": "day1"
    },
    "top_k": {
      "type": "integer",
      "default": 5
    }
  }
}
```

映射到 RAG 服务：

```http
POST /api/v1/eval/run
```

## 5. 安全规则

- MCP Tool 只读。
- 不暴露非知识源引用的本地文件路径。
- 不返回密钥、cookie、token、生产凭据。
- Tool 返回中保留 `trace_id`，方便审计。
- 如果 RAG 服务拒答，MCP Server 必须返回拒答结果，不能让模型继续猜。

## 6. 为什么 MCP 不直接做 RAG

MCP Server 的职责是暴露工具，不是承载 RAG 系统。

如果把文档解析、embedding、vector store、rerank 都放进 MCP Server，会导致：

- MCP Server 太重。
- Agent 工具协议和知识服务耦合。
- 后续前端、Java 服务、CLI 无法复用 RAG 能力。
- RAG 调参需要改 MCP 服务。

因此正确方式是：

```text
RAG Service 负责能力；
MCP Server 负责把能力暴露给 Agent。
```

## 7. 学习顺序

建议先看：

1. `rag-mcp-server/src/ragClient.ts`
2. `rag-mcp-server/src/index.ts`
3. `docs/service-api-design.md`

先理解 MCP Tool 如何映射 HTTP API，不需要一开始深入 MCP 协议细节。
