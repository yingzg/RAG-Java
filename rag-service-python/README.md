# rag-service-python

独立 RAG 知识服务。面向 Java 后端技术文档（Dubbo/DDD/状态机/BFF）的检索增强生成服务。

## 架构

```
离线索引：Markdown → 切块 → metadata → bge-m3 embedding → VectorStore
在线问答：问题 → Hybrid Search(RRF) → Rerank → DeepSeek LLM → Citation校验 → 拒答
```

## 快速启动

### 1. 安装依赖

```bash
cd rag-service-python
pip install -e .
pip install numpy httpx pydantic-settings
```

### 2. 配置 API Key

```bash
cp .env.template .env
# 编辑 .env，填入真实 Key：
#   SILICONFLOW_API_KEY=sk-xxx    （硅基流动，用于 embedding）
#   DEEPSEEK_API_KEY=sk-xxx       （DeepSeek，用于 LLM 生成）
```

> 注意：LLM Key 为空时，`/answer` 自动降级为模板回答（不调 LLM）。

### 3. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

杀进程&重启服务

kill $(lsof -t -i:8000) 2>/dev/null; sleep 1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


浏览器打开：
- **前端 UI**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs

### 4. 建索引（首次）

```bash
curl -X POST http://localhost:8000/api/v1/index/rebuild \
  -H "Content-Type: application/json" \
  -d '{"source_names":[],"mode":"full"}'
```

### 5. 问答测试

```bash
# 搜索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query":"Dubbo 非幂等接口能不能配 retries=2","mode":"hybrid","rerank":true}'

# 问答
curl -X POST http://localhost:8000/api/v1/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"聚合根的设计原则是什么？"}'
```

### 6. 跑 Eval

```bash
curl -X POST http://localhost:8000/api/v1/eval/run \
  -H "Content-Type: application/json" \
  -d '{"case_set":"full","top_k":5}'
```

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 前端问答 UI |
| `/health` | GET | 健康检查 |
| `/docs` | GET | Swagger API 文档 |
| `/api/v1/search` | POST | 检索（支持 keyword/vector/hybrid 三种模式） |
| `/api/v1/answer` | POST | 问答（DeepSeek LLM + 引用 + 拒答） |
| `/api/v1/index/rebuild` | POST | 重建索引 |
| `/api/v1/traces/{trace_id}` | GET | 查询 trace |
| `/api/v1/eval/run` | POST | 跑 eval（30 条 case） |

## 技术栈

| 组件 | 选型 |
|---|---|
| 框架 | Python 3.10+ / FastAPI |
| Embedding | SiliconFlow BAAI/bge-m3（1024 维） |
| LLM | DeepSeek Chat（OpenAI 兼容） |
| 向量存储 | numpy 本地文件（可切 pgvector） |
| 检索 | Hybrid Search（RRF 融合 + RuleBasedReranker） |
| 部署 | Docker Compose（python:3.12-slim） |

## 项目结构

```
app/
├── main.py           # FastAPI 入口
├── settings.py       # pydantic-settings 配置
├── models.py         # API 数据模型
├── schema.py         # 内部数据契约
├── service.py        # 依赖注入编排
├── embedding/        # Embedding 客户端
├── generation/       # LLM + Prompt + Citation + Refusal
├── ingestion/        # 离线索引（loader/chunker/metadata/indexer）
├── retrieval/        # Keyword + Vector + Hybrid + Rerank
├── store/            # VectorStore + ChunkStore
└── eval/             # EvalRunner
frontend/
└── index.html        # 极简问答 UI
```
