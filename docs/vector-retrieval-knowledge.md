# RAG 向量检索知识详解

## 1. Embedding 是什么

Embedding（嵌入）是把文本转成向量的过程。向量是语义的数学表示——它不是关键词匹配，而是将文本的"含义"编码为一组固定长度的浮点数。

核心直觉：语义相近的文本，在向量空间里的距离也相近。例如：

- "接口超时怎么处理"
- "RPC timeout policy"

这两个字符串完全不同（一个中文、一个英文），但表达的是同一个问题。经过 Embedding 模型编码后，它们在高维向量空间中的位置会非常接近。

**核心原则**：文档和 query 必须使用**同一个** embedding 模型。不同模型产出的向量空间互不兼容，跨模型比较没有意义。

---

## 2. 本项目选型：BAAI/bge-m3（1024维）

### 为什么选 bge-m3

| 维度 | bge-m3 | OpenAI text-embedding-3 |
|------|--------|------------------------|
| 中文效果 | 顶尖（专为中文优化） | 尚可（以英文为主） |
| 多语言混合 | 强（中英混合文本表现优秀） | 一般 |
| 调用方式 | SiliconFlow API（OpenAI 兼容） | OpenAI API |
| 成本 | 极低（硅基流动价格低廉） | 较高 |

具体理由：

1. **中文技术文档是主场景**，bge-m3 在中文语义理解上效果顶尖，尤其适合 RAG-Java 项目定位的 Java 技术问答。
2. **中英混合文本常见**，如 `OrderController#createOrder`、`@Transactional` 注解说明等，bge-m3 的 Multilingual 能力强，能同时理解中文语境和英文代码符号。
3. **通过 SiliconFlow（硅基流动）API 调用**，无需自部署模型，成本极低，且接口兼容 OpenAI 格式。
4. **1024 维**在召回效果和存储成本间取得了良好平衡。

### 调用方式

```python
import requests

response = requests.post(
    "https://api.siliconflow.cn/v1/embeddings",
    headers={
        "Authorization": "Bearer <your-api-key>",
        "Content-Type": "application/json"
    },
    json={
        "model": "BAAI/bge-m3",
        "input": "如何排查 RPC 超时问题？"
    }
)

embedding = response.json()["data"][0]["embedding"]  # list[float]，长度 1024
```

接口完全兼容 OpenAI Embedding 格式，现有 OpenAI SDK 可直接复用，只需替换 `base_url` 和 `api_key`。

---

## 3. 向量存储：LocalVectorStore → pgvector

### 起步方案：LocalVectorStore（numpy + JSON）

文件结构：

```
data/index/
├── vectors.npy       # numpy 二维数组，shape = (N, 1024)
└── chunk_ids.json    # ["chunk_001", "chunk_002", ...] 与 vectors.npy 按行对应
```

| 优点 | 缺点 |
|------|------|
| 零外部依赖，本地即可跑通全链路 | 无并发支持（单进程读写） |
| 实现简单，适合快速验证 | 增量写入困难（需重写整个 .npy） |
| 几百个向量毫秒级查询 | 全量加载到内存，规模受限 |

### 生产方案：PostgreSQL + pgvector

pgvector 是 PostgreSQL 的向量扩展插件，提供原生向量数据类型和相似度运算符。

```sql
-- 建表
CREATE TABLE vectors (
    chunk_id   TEXT PRIMARY KEY,
    embedding  VECTOR(1024),           -- pgvector 向量类型
    metadata   JSONB
);

-- 向量相似度搜索（一条 SQL）
SELECT chunk_id, 1 - (embedding <=> :query_vector) AS similarity
FROM vectors
ORDER BY embedding <=> :query_vector
LIMIT 10;
```

| 特性 | LocalVectorStore | pgvector |
|------|-----------------|----------|
| 并发查询 | 不支持 | 原生支持 |
| 增量写入 | 困难 | 原生 INSERT/UPDATE/DELETE |
| 索引加速 | 无 | 支持 IVFFlat / HNSW 近似索引 |
| 部署复杂度 | 零 | 需 PostgreSQL 实例 |

两种方案通过统一的 `VectorStore` 接口切换，上层检索代码零改动。

---

## 4. 相似度计算：余弦相似度（Cosine Similarity）

### 公式

余弦相似度衡量两个向量在方向上的接近程度：

$$\text{cosine}(A, B) = \frac{A \cdot B}{\|A\| \times \|B\|}$$

取值范围 `[-1, 1]`，实际使用中通常为 `[0, 1]`（bge-m3 输出已归一化）。

### 为什么选余弦相似度

- bge-m3 输出默认归一化（向量模长为 1），余弦相似度与内积等价，计算更简单
- 语义检索关注"方向"而非"长度"，余弦相似度天然匹配这一需求

### 性能

- 几百个 1024 维向量的 numpy 批量计算：≈ 1-5ms
- 真正的延迟瓶颈在外部 API 调用（SiliconFlow embedding API 往返约 200-500ms）

```python
import numpy as np

def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    return np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

def batch_search(query_vec: np.ndarray, matrix: np.ndarray, top_k: int) -> list[tuple[int, float]]:
    """返回 (index, similarity) 按相似度降序排列"""
    scores = np.dot(matrix, query_vec)  # 已归一化时可用内积替代余弦
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(int(i), float(scores[i])) for i in top_indices]
```

---

## 5. VectorStore 接口设计（本项目契约）

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass, field


@dataclass
class VectorItem:
    chunk_id: str
    embedding: list[float]
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    chunk_id: str
    score: float
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """向量存储统一契约。LocalVectorStore 和 PgvectorStore 均实现此接口。"""

    def upsert(self, items: list[VectorItem]) -> None:
        """插入或更新向量。chunk_id 已存在则覆盖，否则新增。"""
        ...

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[VectorHit]:
        """余弦相似度搜索，返回 top_k 个最相似向量。"""
        ...

    def delete(self, chunk_ids: list[str]) -> int:
        """删除指定 chunk 的向量，返回实际删除数。"""
        ...

    def count(self) -> int:
        """返回已存储的向量数量。"""
        ...

    def clear(self) -> None:
        """清空全部向量。"""
        ...
```

### 为什么需要 upsert 和 delete

| 场景 | 操作 | 说明 |
|------|------|------|
| 文档更新 | `upsert` | 文档内容变更后，重新分 chunk 并覆盖旧向量，无需清空重建 |
| 文档删除 | `delete` | 删除文档对应的全部 chunk 向量，避免返回已失效内容 |
| 增量索引 | `upsert` | 新增文档时只索引新 chunk，不影响已有索引 |

三个场景合一：**支持索引的增量维护，避免全量重建的高昂成本。**

---

## 6. 切换 VectorStore 的流程

### 配置切换

```yaml
# application.yml
rag:
  vector_store: "pgvector"   # "local" | "pgvector"
```

### 切换步骤

1. 修改配置项 `rag.vector_store` 为目标存储类型
2. 手动触发索引重建 API：

```
POST /api/v1/index/rebuild
```

3. 重建期间所有检索请求返回状态码 `503`，响应体：

```json
{
  "code": 503,
  "message": "索引重建中，请稍后重试"
}
```

### 为什么不做自动切换

索引重建是**变更操作**，涉及：
- 全量文档重新 embedding（调用外部 API，有成本和时间开销）
- 旧索引数据的保留或清除策略

这些决策需要人来确认，不应由代码静默执行。

---

## 7. Embedding 模型更换的影响

### 核心约束

**query embedding 和存储 embedding 必须来自同一模型。**

换模型后必须全量重建索引，原因：

- 每个 embedding 模型有自己的向量空间。bge-m3 的 1024 维空间和 OpenAI text-embedding-3 的 1536 维空间完全不兼容。
- 即使维度相同，不同模型的语义编码方式不同——同一段文本在模型 A 和模型 B 下的向量没有可比性。
- 用旧模型的向量去匹配新模型的 query 向量，结果等同于随机。

### 换模型的操作清单

1. 修改 embedding 模型配置
2. 清空 `VectorStore`（调用 `clear()`）
3. 触发全量索引重建
4. 验证新模型下的召回效果

---

## 8. 常见面试追问

### Q: bge-m3 和 OpenAI embedding 怎么选？

**A:** 看场景。中文为主选 bge-m3，英文为主选 OpenAI。混合场景（中英文代码注释、技术文档）bge-m3 的多语言能力更强，且通过 SiliconFlow 调用成本更低。

### Q: 1024 维够不够？

**A:** 够。维度不是越大越好——768/1024 是性价比甜点。1536 维以上存储和计算成本显著上升，但召回效果的提升边际递减。MTEB 基准测试也表明 1024 维在大多数场景下与更高维度的差距很小。

### Q: 向量检索一次要多久？

**A:** 计算本身是毫秒级（numpy 批量余弦相似度 ≈ 1-5ms）。真正的瓶颈在 embedding API 的网络往返（SiliconFlow 约 200-500ms）。优化方向：对 query 做缓存，避免重复 embedding。

### Q: 如果向量越来越多怎么办？

**A:** 分阶段演进：

| 阶段 | 方案 | 适用规模 |
|------|------|---------|
| 起步 | numpy 全量加载到内存 | < 1万条 |
| 增长 | pgvector + HNSW 近似索引 | 1万 - 100万条 |
| 大规模 | Milvus / Qdrant 专用向量数据库 | > 100万条 |

### Q: 怎么证明向量检索比关键词好？

**A:** 用 eval 对比实验：

1. 构造测试集——包含"同一语义、不同表达"的问题对（如"接口超时" vs "RPC timeout"）
2. 分别跑关键词检索（BM25）和向量检索，对比 `recall@k`
3. 向量检索应在语义等价但字面不同的查询上召回率显著高于关键词

关键词检索的盲区——"超时"匹配不到 "timeout"——正是向量检索的优势所在。

---

## 9. 关键词

`RAG` `embedding` `bge-m3` `向量检索` `cosine similarity` `pgvector` `numpy` `VectorStore` `RRF` `SiliconFlow` `中文 embedding`
