# Phase 1-3 实施计划与待完善清单

> 日期：2026-08-11（最后更新）  
> 状态：Phase 1-3 核心链路已完成，以下为待完善项

---

## 已完成

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 1 | 索引+检索：schema/embedding/vector/hybrid/rerank | ✅ |
| Phase 2 | 生成+服务：DeepSeek LLM/Prompt/Citation/Refusal | ✅ |
| Phase 3 | Eval+部署：30 case/MRR 0.589/Dockerfile/前端UI | ✅ |

---

## 0. 现状回顾

| 维度 | 当前状态 | Phase 1 目标 |
|---|---|---|
| 文档索引 | 依赖 prototype-cli 产出 JSONL，Python 端只读 | Python 端自建索引链路 |
| 检索方式 | 纯关键词（O(n) 线性扫描 + 启发式评分） | Keyword + Vector → RRF 融合 Hybrid |
| Embedding | 无 | SiliconFlow bge-m3 (1024 维) |
| 向量存储 | 无 | numpy 本地文件 (LocalVectorStore) |
| Rerank | 无 | RuleBasedReranker |
| 配置 | 3 个硬编码 Path | pydantic-settings 环境变量驱动 |
| 依赖 | fastapi/uvicorn/pydantic | + numpy/httpx/pydantic-settings |

---

## 待完善（按优先级）

### P0 🔴 配 API Key + 真实 hybrid search 验证

**当前状态**：EmbeddingClient/VectorStore/HybridRetriever 代码已完成，但从未用真实 API 调用过。当前 eval 跑的是关键词检索，不是 hybrid search。

**要做**：
- [x] SiliconFlow API Key 已配置
- [ ] 测试 SiliconFlowEmbeddingClient 真实调用
- [ ] POST /api/v1/index/rebuild 跑通真实 embedding
- [ ] 跑 eval 对比关键词 vs hybrid 的 Recall@5/MRR
- [ ] 产出对比报告

**面试价值**：从"代码写好了"变成"我的数据显示向量比关键词 Recall 提升 X%"。

---

### P1 🔴 trace 结构化

**当前状态**：`service.py` 写 trace 是通用 dict，未用 `schema.RagTrace` dataclass。字段不全——缺 `retrieved_chunks`、`prompt_version`、`query_rewritten` 等。

**要做**：
- `service.py` 的 `_write_trace` 改为按 `RagTrace` 结构序列化
- 补充 `_to_trace_chunks()` 方法：把 ScoredChunk 转为 TraceRetrievedChunk
- 验证 `/api/v1/traces/{trace_id}` 返回完整字段

**面试价值**：可观测性是生产 RAG 的基本要求，trace 不全 = 答错时无法定位是检索失败还是生成失败。

---

### P1 🔴 MCP Server 字段对齐

**当前状态**：`rag-mcp-server/src/ragClient.ts` 的类型定义还是旧的，不包含 `keyword_score/vector_score/rerank_score/retriever/tokens/refusal_reason` 等新字段。

**要做**：
- TypeScript 端类型定义补全新字段
- MCP 三工具（doc.search/rag.answer/rag.eval.run）返回新字段
- 验证 Agent 通过 MCP 调用能拿到完整数据

**面试价值**：MCP 是 Agent 集成入口，字段不全 = Agent 拿不到检索质量信号。

---

### P2 🟡 Docker 部署验证

**当前状态**：Dockerfile + docker-compose.yml 已编写，未在目标服务器上验证。

**要做**：
- [ ] `docker compose up` 验证服务可启动
- [ ] curl 测试所有端点
- [ ] 浏览器打开前端 UI 验证

**面试价值**：从"本地项目"变成"可以发 URL 给面试官演示"。

---

### P2 🟡 增量索引

**当前状态**：`IndexService.rebuild()` 是全量重建。`VectorStore.upsert/delete` 已就绪但增量逻辑未实现。

**要做**：
- 文档变更检测（content_hash 对比）
- 增量 rebuild：只处理变更文档
- 对比新旧 chunk → 新增 upsert、修改 upsert、删除 delete

---

### P3 🟢 可选增强

| 功能 | 价值 | 难度 |
|---|---|---|
| **QueryRewriter** | 口语→检索查询改写，面试加分 | 中 |
| **pgvector 升级** | 替换 numpy，支持并发增量 | 中 |
| **流式输出 SSE** | /answer 流式 token，体验更好 | 低 |
| **LLM-as-judge** | eval 自动打分，不用人工 | 中 |
| **parent-child chunk** | 小块检索+大块回答 | 高 |
| **前端增强** | 历史记录/反馈按钮/移动端适配 | 低 |

---

## 验收标准（最终）

- [x] `/index/rebuild` 加载→切块→embedding→入库
- [x] `/search?mode=hybrid` 返回 keyword/vector/rerank 分
- [x] `/answer` 接 DeepSeek + 引用 + 拒答
- [x] `/eval/run` ≥30 case + Recall@5/MRR
- [ ] trace 结构化（RagTrace 完整字段）
- [ ] MCP `doc.search`/`rag.answer`/`rag.eval.run` 对齐新字段
- [ ] `docker compose up` 在 2G 机器可起
- [ ] 关键模块有中文注释 + 面试口径
