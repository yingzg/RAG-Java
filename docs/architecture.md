# RAG 知识服务架构说明

## 1. 项目定位

本项目把 RAG 定位为一个独立的“知识上下文服务”，而不是嵌入到某个 Java 业务服务里的功能模块。

RAG 服务负责把私有知识转换成大模型和 Agent 可使用的上下文：

- 可检索
- 可引用
- 可拒答
- 可追踪
- 可评估
- 可持续优化

它的职责边界更接近“知识基础设施”，而不是订单、客户、审批、交易这类确定性业务逻辑。

## 2. 总体架构

```text
知识源
  - Markdown 技术文档
  - Java 代码规范
  - Dubbo / DDD / 状态机 / BFF 文档
  - 后续可扩展：Wiki、飞书、Git 仓库、数据库 Schema、故障案例
        |
        v
RAG Knowledge Service
  - 文档接入 ingestion
  - 文档清洗 cleaning
  - 文档切块 chunking
  - metadata 与权限标记
  - 关键词索引
  - 向量索引
  - hybrid retrieval
  - rerank
  - 答案生成
  - 引用与拒答
  - trace 与 eval
        |
        +--> 向量库 / 搜索引擎
        +--> LLM / Embedding / Rerank 模型服务
        |
        v
外部调用方
  - TypeScript MCP Server
  - Agent workflow
  - Java 业务服务
  - 知识库前端页面
  - CLI / 管理工具
```

## 3. 为什么 RAG 不放进 Java 业务服务

RAG 拥有一套独立生命周期：

- 文档导入
- 文档解析
- 文档清洗
- chunk 切块
- embedding
- 向量索引
- 关键词索引
- 检索和重排
- prompt 构造
- 答案生成
- 引用校验
- 拒答策略
- eval 测试
- trace 追踪

如果把这些能力放进普通 Java 业务服务，会带来几个问题：

- 业务服务职责变重。
- AI 依赖、向量库、模型配置和业务逻辑耦合。
- RAG 调参会影响业务服务发布。
- 多个业务系统很难复用同一个知识能力。
- eval、trace、安全策略会污染业务工程结构。

因此更合理的边界是：

```text
Java 业务服务可以调用 RAG，但不应该承载 RAG 内部复杂度。
```

## 4. 运行时职责边界

### 4.1 RAG 服务负责

- 知识源配置。
- 索引重建和后续增量索引。
- chunk schema 与 metadata schema。
- search / answer API。
- prompt 与引用策略。
- 拒答策略。
- trace 与 eval 数据。
- 后续向量库、搜索引擎、LLM、embedding、rerank 的接入。

### 4.2 MCP Server 负责

- MCP 协议传输。
- Tool schema 定义。
- 把 `doc.search` / `rag.answer` 映射到 RAG HTTP API。
- 面向 Agent 返回结构化结果和错误信息。

MCP Server 不负责：

- 文档解析。
- chunk。
- embedding。
- 向量库查询。
- RAG eval。

### 4.3 Java 业务服务负责

- 业务逻辑。
- 事务。
- 领域模型。
- 数据库读写。
- 自己系统内的数据权限判断。
- 在需要 AI 上下文时调用 RAG 服务。

Java 业务服务不应该负责：

- chunk。
- embedding。
- vector index。
- prompt 构造。
- RAG eval。
- RAG trace。

## 5. 子项目职责

### 5.1 `prototype-cli`

Java CLI 原型，已经完成 Day1 能力。

它的作用是学习和诊断：

- Markdown 文档加载。
- Markdown 标题切块。
- metadata 提取。
- JSONL 本地索引。
- 关键词检索。
- 模板化回答。
- 引用和拒答。
- trace 和 eval。

它不是生产查询入口。

### 5.2 `rag-service-python`

正式 RAG 独立服务骨架。

当前阶段：

- 读取 `prototype-cli` 生成的 JSONL chunk。
- 暴露 HTTP API。
- 支持 search / answer / trace / eval 的接口形态。
- 内置 Python 版本关键词检索。

后续阶段：

- 自己负责文档导入。
- 接 embedding。
- 接向量库。
- 实现 hybrid retrieval。
- 实现 rerank。
- 接 LLM 生成答案。
- 实现 metadata filter。

### 5.3 `rag-mcp-server`

TypeScript MCP 适配层。

它暴露：

- `doc.search`
- `rag.answer`
- `rag.eval.run`

它通过 HTTP 调用 `rag-service-python`，不重复实现 RAG 检索逻辑。

## 6. 演进路线

```text
Day1    Java prototype-cli 已完成，用来理解 RAG 机制
Day1.5  架构纠偏，拆出 Python RAG 服务和 TS MCP 骨架
Day2    embedding + vector store
Day3    hybrid search + rerank + LLM answer
Day4    MCP server 集成
Day5    eval / trace / bad case / 面试材料
```

## 7. 当前项目状态

当前项目处于 Day1.5：

- Java 原型可运行。
- Python 服务骨架已建立。
- TypeScript MCP 骨架已建立。
- 正式 RAG 服务还没有接 embedding、向量库和 LLM。

因此当前项目是“架构方向正确的 RAG 学习与生产雏形项目”，不是最终生产级 RAG。
