# 技术语言选型决策

日期：2026-06-15

## 1. 最终决策

正式 RAG 服务使用 **Python FastAPI**。

MCP 适配层使用 **TypeScript**。

已有 Java CLI 保留为 `prototype-cli`，用于学习、排查、离线诊断和机制验证。

## 2. 为什么不把 RAG 放进 Java 业务服务

RAG 不是普通业务逻辑。它有独立的工程生命周期：

- 文档导入
- 文档解析和清洗
- chunk 切块
- metadata 与权限标记
- embedding
- 向量索引和关键词索引
- retrieval 检索
- rerank 重排
- prompt 构造
- 答案生成
- 引用校验
- 拒答策略
- eval 和 trace

如果把这些能力放进 Java 订单、客户、Dubbo Provider、CRM BFF 这类业务服务里，会把 AI 基础设施和业务交付耦合在一起。

结果通常是：

- 业务工程变复杂。
- RAG 调参影响业务服务发布。
- 文档索引任务和业务请求混在一起。
- 向量库、模型客户端、prompt、trace、eval 污染业务代码。
- 多个业务系统难以复用同一套知识服务。

因此，RAG 应该作为独立服务存在。

业务服务可以调用 RAG，但不应该拥有 RAG 内部实现。

## 3. 为什么正式 RAG 服务选 Python

Python 更适合当前项目的正式 RAG 服务，原因是：

- RAG 实验迭代速度快。
- LangChain、LlamaIndex、RAGAS 类评估工具、embedding client、rerank 集成、文档处理工具更成熟。
- RAG 服务是独立 HTTP 服务，Java 系统仍然可以通过 API 干净接入。
- 避免误导成“Java 业务后端应该承载 RAG 内部复杂度”。

换句话说：

```text
Python 负责 RAG 能力本身；
Java 负责业务系统和工程集成；
HTTP API 负责解耦。
```

## 4. 为什么 MCP 适配层选 TypeScript

MCP 和 Agent 工具链生态中，TypeScript 和 Python 更常见。

本项目选择 TypeScript 做 MCP Server，原因是：

- MCP Tool schema 写起来自然。
- 与 AI IDE、Agent、JSON schema、HTTP adapter 结合顺畅。
- 可以保持 MCP Server 很薄，只做协议适配和工具暴露。

目标结构：

```text
Agent / IDE / Skill
  -> TypeScript MCP Server
  -> Python RAG Knowledge Service
  -> Vector/Search/LLM providers
```

## 5. Java 在项目中的价值

Java 仍然重要，但不是用来隐藏 RAG 内部复杂度。

Java 的价值在于：

- 你的核心知识源是 Java 后端技术文档：Dubbo、DDD、BFF、状态机。
- Java 业务系统未来可以通过 HTTP 调用 RAG 服务。
- Java 后端经验可以帮助你讲清楚服务边界、权限、审计、可靠性、部署和工程治理。
- 后续可以提供 Java SDK 或 Spring Boot client，方便企业系统调用 RAG。
- 当前 `prototype-cli` 作为学习原型，帮助你看懂 RAG 的底层机制。

## 6. 面试表达

可以这样讲：

> 我先用 Java CLI 手写了一个 RAG 原型，用来理解 RAG 的基础机制，包括文档加载、chunk、metadata、检索、引用、拒答、trace 和 eval。但我不会把这个作为生产实现放进 Java 业务服务。生产形态是独立 RAG Knowledge Service，用 Python 实现 RAG 能力，用 TypeScript MCP Server 对 Agent 暴露工具，Java 业务服务通过 HTTP 调用它。这样既保留 Java 后端工程经验，又符合 AI 工具链生态和微服务解耦原则。

## 7. 当前选型结论

```text
prototype-cli       Java，学习与诊断原型
rag-service-python  Python FastAPI，正式 RAG 服务
rag-mcp-server      TypeScript，MCP 工具适配层
Java 业务系统       未来作为调用方，不承载 RAG 内部实现
```
