# RAG 检索与评分设计：从关键词检索到生产级 Hybrid Search

## 1. 文档目的

本文总结生产 RAG 中“检索、评分、融合、重排、上下文组装、引用校验和 eval 评估”的核心设计。

它不是对当前 Java `KeywordRetriever` 的逐行解释，而是帮助你建立生产级 RAG 的正确心智模型：当前 Java 实现只是一个透明的学习版 baseline，真实生产系统通常会使用 Elasticsearch / OpenSearch / Lucene / Solr / Vespa、向量库、reranker 和自动化 eval 来完成检索质量控制。

适用场景：

- 理解 Day1 Java `KeywordRetriever` 到生产检索系统之间的映射关系；
- 设计轻量到中级生产 RAG 的检索链路；
- 面试时清楚说明 BM25、metadata filter、RRF、reranker、citation 和 eval；
- 后续将 Java 原型迁移到 Python 服务时，判断哪些逻辑应该保留，哪些应该替换为搜索引擎或模型能力。

相关材料：

- 当前学习笔记：`docs/learning/day1/04-keyword-retriever.md`
- 当前 Java 实现：`prototype-cli/src/main/java/com/example/rag/retrieval/KeywordRetriever.java`
- 当前分词实现：`prototype-cli/src/main/java/com/example/rag/retrieval/QueryTokenizer.java`
- 切块设计：`docs/chunking-design.md`

## 2. 先记住十句话

1. **生产 RAG 不应该主要靠手写 `contains` 和人工加分规则。**
2. **关键词检索通常交给 Elasticsearch / OpenSearch / Lucene 这类倒排索引系统。**
3. **BM25 分数是在查询时动态计算的，不是在写入索引时给每个词固定打分。**
4. **metadata filter 是结构化过滤，类似 SQL `where`，多数情况下不走正文分词。**
5. **字段权重是生产检索的核心手段，例如标题命中比正文命中更重要。**
6. **向量检索解决语义相似，BM25 解决关键词精确匹配，二者应该互补。**
7. **RRF 用排名融合多个召回结果，不直接相加 BM25 分和向量相似度。**
8. **reranker 是精排器，重点判断 chunk 是否真的能回答问题。**
9. **上下文组装不是简单拼接 topK，而是要控制 token、去重、合并相邻块和绑定 citation。**
10. **生产 eval 不只统计成功失败，还要拆分 Recall@K、MRR、nDCG、Groundedness、Citation Correctness 等指标。**

## 3. 当前 Java KeywordRetriever 应该如何理解

当前 Java `KeywordRetriever` 是一个教学用的透明检索器，它的流程可以简化成：

```text
用户问题
  ↓
QueryTokenizer 拆出关键词
  ↓
遍历所有 chunk
  ↓
对每个 chunk 手写评分
  ↓
只保留 score > 0 的结果
  ↓
按 score 从高到低排序
  ↓
返回 topK
```

它的价值不是让你学习“生产环境应该这么写检索器”，而是让你看懂检索系统背后的几个基本概念：

| 当前 Java 概念 | 生产系统中的对应概念 |
|---|---|
| `QueryTokenizer` | Analyzer / Query Parser / Query Rewrite |
| 遍历所有 chunk | 倒排索引候选召回 |
| `sectionPath +8` | 字段权重，field boost |
| `fileName +6` | 文件名 / 标题字段加权 |
| `sourceName +5` | 来源权重 / 业务权重 |
| 正文出现次数 `+2` | term frequency |
| `matchedTerms` | 命中词 / highlight |
| `matchReasons` | explain / trace |
| `sort by score desc` | 排序 |
| `topK` | 召回候选数量 |

你不需要死磕这些细节：

- 正则如何拆词；
- 中文 2-gram / 3-gram 的具体实现；
- 为什么标题是 `+8` 而不是 `+10`；
- 为什么正文每次命中是 `+2`；
- `countOccurrences` 的代码细节；
- Java 集合、Comparator、Stream 写法。

你真正需要理解的是：

```text
检索 = 查询分析 + 候选召回 + 评分排序 + topK 返回 + trace 解释
```

## 4. 生产 RAG 的完整检索流程

生产 RAG 中，一个典型查询链路通常是：

```text
用户问题
  ↓
查询理解 / query rewrite
  ↓
metadata filter 缩小搜索范围
  ↓
BM25 关键词召回
  ↓
向量召回
  ↓
RRF 融合多个召回列表
  ↓
reranker 重排
  ↓
上下文组装
  ↓
LLM 基于证据生成答案
  ↓
citation 校验 / grounding 校验
  ↓
trace 记录
  ↓
eval 评估
```

这条链路的关键点是：每一层解决的问题不同。

| 阶段 | 解决的问题 |
|---|---|
| query rewrite | 用户问题不完整、口语化、缺少领域词 |
| metadata filter | 应该在哪个范围内搜索 |
| BM25 | 精确关键词、术语、代码、错误码、实体名召回 |
| vector search | 语义相似、表达不同但意思相近的问题召回 |
| RRF | 多个召回列表如何稳定融合 |
| reranker | 候选 chunk 谁最能回答问题 |
| context assembly | 哪些证据进入 prompt，如何组织 |
| LLM answer | 基于证据生成自然语言答案 |
| citation check | 答案中的结论是否真的有依据 |
| eval | 检索和回答质量是否可量化、可回归 |

## 5. Metadata Filter：生产里如何过滤

### 5.1 Metadata filter 不是正文 contains

metadata filter 通常是结构化过滤，类似数据库 SQL 的 `where` 条件。

例如每个 chunk 入库时携带 metadata：

```json
{
  "chunk_id": "dubbo_exception_003",
  "content": "Dubbo 服务异常需要统一封装为 BizException...",
  "title": "Dubbo 异常处理规范",
  "section_path": "服务治理 / Dubbo / 异常处理",
  "source_id": "backend_knowledge_base",
  "tenant_id": "tenant_a",
  "project": "payment",
  "doc_type": "deep_dive",
  "language": "zh",
  "version": "v3",
  "status": "published",
  "acl_users": ["u001", "u002"],
  "created_at": "2026-06-01"
}
```

查询时可能构造 filter：

```json
{
  "tenant_id": "tenant_a",
  "project": "payment",
  "doc_type": ["deep_dive", "faq"],
  "status": "published",
  "language": "zh",
  "acl_users": "u001",
  "created_at": {
    "gte": "2025-01-01"
  }
}
```

这一步表达的是：

```text
只在当前租户查；
只查 payment 项目；
只查 deep_dive / faq 类型；
只查已发布文档；
只查中文文档；
只返回当前用户有权限看的内容；
只查 2025-01-01 之后的文档。
```

### 5.2 ES / OpenSearch 中的 filter 示例

简化 DSL：

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenant_id": "tenant_a" } },
        { "term": { "project": "payment" } },
        { "terms": { "doc_type": ["deep_dive", "faq"] } },
        { "term": { "status": "published" } },
        { "term": { "language": "zh" } },
        { "term": { "acl_users": "u001" } },
        { "range": { "created_at": { "gte": "2025-01-01" } } }
      ],
      "must": [
        {
          "multi_match": {
            "query": "Dubbo 服务异常如何封装",
            "fields": ["title^5", "section_path^3", "summary^2", "content"]
          }
        }
      ]
    }
  }
}
```

其中：

- `filter` 负责结构化过滤；
- `must` 负责正文相关性检索；
- `title^5` 表示标题字段权重更高；
- `section_path^3` 表示章节路径权重更高；
- `content` 是正文基础权重。

### 5.3 哪些 metadata 通常不分词

| 字段 | 典型类型 | 是否分词 | 用法 |
|---|---|---:|---|
| `tenant_id` | keyword | 否 | 多租户隔离 |
| `project` | keyword | 否 | 项目过滤 |
| `source_id` | keyword | 否 | 知识库过滤 |
| `doc_type` | keyword | 否 | 文档类型过滤 |
| `status` | keyword | 否 | published / draft / archived |
| `version` | keyword | 否 | 版本过滤 |
| `acl_users` | keyword array | 否 | 权限过滤 |
| `created_at` | date | 否 | 时间范围 |
| `priority` | number | 否 | 业务排序 |

### 5.4 哪些 metadata 可能参与分词检索

| 字段 | 用法 |
|---|---|
| `title` | 高权重检索字段 |
| `section_path` | 高权重检索字段，也可用于展示定位 |
| `summary` | 中高权重检索字段 |
| `tags_text` | 如果标签是自然语言，可参与检索 |
| `file_name_text` | 文件名如果含业务语义，可参与检索 |

结论：

```text
metadata filter 主要是结构化过滤；
文本型 metadata 可以额外参与 BM25 检索；
不要把所有 metadata 都当正文 contains 来处理。
```

## 6. BM25：生产关键词检索的基础评分

### 6.1 BM25 解决什么问题

BM25 是生产关键词检索里非常常见的基础排序算法。它解决的问题是：

```text
给定用户 query 和一批文档，哪些文档在关键词层面最相关？
```

它比简单 `contains` 更强，因为它会考虑：

1. 查询词是否命中；
2. 查询词命中了多少个；
3. 某个词在当前文档出现几次；
4. 某个词在全库是否稀有；
5. 当前文档或字段是不是过长；
6. 不同字段是否有不同权重。

### 6.2 写入索引时发生什么

假设 chunk 内容是：

```text
Dubbo 服务异常需要统一封装为 BizException。
```

搜索引擎会通过 analyzer 分词，得到类似：

```text
dubbo
服务
异常
统一
封装
bizexception
```

然后建立倒排索引：

```text
dubbo        -> chunk_1, chunk_7, chunk_20
服务         -> chunk_1, chunk_2, chunk_9
异常         -> chunk_1, chunk_5, chunk_7
封装         -> chunk_1, chunk_8
bizexception -> chunk_1, chunk_11
```

同时记录统计信息：

| 统计项 | 含义 |
|---|---|
| TF | term frequency，词在当前文档或字段出现几次 |
| DF | document frequency，词出现在多少文档中 |
| IDF | inverse document frequency，词越稀有，区分度越高 |
| field length | 当前字段长度 |
| avg field length | 全库平均字段长度 |

### 6.3 查询时才动态计算分数

用户查询：

```text
Dubbo 服务异常如何封装
```

分词后：

```text
dubbo
服务
异常
封装
```

BM25 可以直观理解为：

```text
BM25 分数 = 每个 query term 对当前 chunk 的贡献之和
```

某个词的贡献大概受这些因素影响：

```text
这个词是否命中；
这个词在当前 chunk 出现几次；
这个词在全库是否稀有；
当前字段长度是否过长；
字段是否被加权。
```

例如：

- `Dubbo`、`BizException` 这类词比较稀有，命中后贡献更大；
- `服务` 这类词很常见，区分度较低，贡献较小；
- 一个 chunk 命中 `Dubbo + 异常 + 封装`，通常比只命中 `Dubbo` 更相关；
- 太长的 chunk 即使命中很多词，也可能被长度归一化削弱，避免长文档天然占便宜。

### 6.4 BM25 分数不是写入时固定写死

容易误解的一点是：

```text
不是文档切块后，写入 ES 时就给每个词固定一个分数，然后查询时直接累加。
```

更准确的是：

```text
写入阶段：分词，建立倒排索引，记录统计信息；
查询阶段：根据 query、倒排索引和统计信息动态计算 BM25 分；
排序阶段：再叠加字段权重、业务权重、时间权重或 reranker 分。
```

因此，生产系统里你通常不需要手写：

```java
if (title.contains(token)) score += 8;
if (content.contains(token)) score += 2;
```

你要设计的是：

- index mapping；
- analyzer；
- 字段结构；
- query DSL；
- field boost；
- metadata filter；
- function score；
- eval 调参。

## 7. 字段权重：标题、章节、正文如何影响评分

生产检索里，字段权重是非常重要的设计。

同样命中 `Dubbo 异常封装`，命中标题通常比命中正文更重要：

```json
{
  "multi_match": {
    "query": "Dubbo 服务异常如何封装",
    "fields": [
      "title^5",
      "section_path^3",
      "summary^2",
      "content"
    ]
  }
}
```

含义：

| 字段 | 权重含义 |
|---|---|
| `title^5` | 标题命中非常重要 |
| `section_path^3` | 章节路径命中较重要 |
| `summary^2` | 摘要命中有额外价值 |
| `content` | 正文基础权重 |

这和 Java 原型里的：

```text
sectionPath +8
fileName +6
sourceName +5
content occurrence +2
```

思想类似，都是“字段命中不应该同等对待”。

区别是：

| Java 原型 | 生产系统 |
|---|---|
| 手写固定加分 | 搜索引擎 BM25 + field boost |
| 全量遍历 chunk | 倒排索引召回 |
| 简单 contains | analyzer + query parser |
| 分数规则写死在代码里 | 查询 DSL 和配置可调 |
| 适合学习和小数据 | 适合生产规模 |

## 8. Function Score：业务权重如何参与排序

除了 BM25 分数，生产系统还可能引入业务权重：

- 官方文档优先；
- 新文档适度优先；
- 高质量文档优先；
- 用户常访问文档优先；
- 当前项目文档优先；
- 过期文档降权。

写入索引时可以保存：

```json
{
  "doc_quality": 0.9,
  "authority_level": 3,
  "is_official": true,
  "updated_at": "2026-06-01",
  "click_count": 120
}
```

查询时使用 function score：

```json
{
  "function_score": {
    "query": {
      "multi_match": {
        "query": "Dubbo 服务异常如何封装",
        "fields": ["title^5", "section_path^3", "content"]
      }
    },
    "functions": [
      {
        "filter": { "term": { "is_official": true } },
        "weight": 1.5
      },
      {
        "field_value_factor": {
          "field": "doc_quality",
          "factor": 1.2
        }
      }
    ]
  }
}
```

这不是替代 BM25，而是在 BM25 相关性的基础上叠加业务排序信号。

需要注意：

```text
业务权重不能过强，否则会把“不相关但权威”的文档排到前面；
相关性分数仍然应该是主信号。
```

## 9. 向量召回：补足关键词检索的短板

BM25 擅长精确匹配：

- 错误码；
- 类名；
- 接口名；
- 产品名；
- 专有名词；
- 明确关键词；
- SQL 字段名；
- 配置项名称。

但 BM25 不擅长处理表达差异很大的问题。

例如用户问：

```text
接口调用老是卡住怎么办？
```

文档里写的是：

```text
RPC 请求超时排查方法
```

BM25 不一定能很好匹配，因为 `卡住` 和 `超时` 字面不同。

向量召回会把 query 和 chunk 转成 embedding，通过语义相似度找内容：

```text
用户 query -> query embedding
chunk 内容 -> document embedding
计算 cosine similarity / dot product
返回语义上最接近的 chunks
```

向量检索适合：

- 同义表达；
- 口语化问题；
- 概念解释；
- 业务意图相近但关键词不同；
- 跨语言或弱关键词问题。

生产 RAG 通常不会只用 BM25，也不会只用向量，而是使用 hybrid search。

## 10. Hybrid Search：BM25 + Vector

Hybrid Search 的基本思想：

```text
BM25 负责精确关键词召回；
Vector 负责语义相似召回；
二者合并后交给 reranker 精排。
```

典型流程：

```text
用户问题
  ↓
metadata filter
  ↓
BM25 top 50
  ↓
Vector top 50
  ↓
RRF 融合 top 100
  ↓
reranker 重排 top 20
  ↓
取 top 5 ~ top 10 进入上下文
```

这样做的好处：

| 检索方式 | 优点 | 短板 |
|---|---|---|
| BM25 | 精确、可解释、对代码/术语/错误码友好 | 不懂语义同义 |
| Vector | 语义强、适合口语化问题 | 对精确实体和数字可能不稳定 |
| Hybrid | 兼顾精确匹配和语义匹配 | 系统复杂度更高，需要 eval 调参 |

## 11. RRF：多个召回列表如何融合

### 11.1 为什么不能直接相加 BM25 分和向量分

BM25 分数和向量相似度不是一个量纲。

BM25 可能是：

```text
A = 12.8
B = 9.1
C = 7.3
```

向量相似度可能是：

```text
D = 0.82
A = 0.79
E = 0.75
```

直接相加没有明确意义，因为两个分数的范围、分布和含义都不同。

### 11.2 RRF 的核心思想

RRF，全称 Reciprocal Rank Fusion，中文可以理解为“倒数排名融合”。

它不直接比较原始分数，而是比较排名：

```text
一个 chunk 如果在多个召回通道里都排名靠前，它更可信。
```

公式简化为：

```text
RRF_score(doc) = Σ 1 / (k + rank_i)
```

常见 `k = 60`。

假设：

```text
BM25 排名：
1. A
2. B
3. C

Vector 排名：
1. D
2. A
3. E
```

那么：

```text
A 在 BM25 第 1，Vector 第 2，两边都靠前，融合分较高；
D 只在 Vector 第 1，也有较高分；
B 只在 BM25 第 2，分数中等；
E 只在 Vector 第 3，分数中等偏低。
```

融合后可能是：

```text
A, D, B, E, C
```

### 11.3 RRF 解决什么问题

RRF 解决的是：

```text
多个召回器的结果怎么合并成一个候选列表？
```

它不是最终答案质量保证，也不是精排模型。

它的输出通常还需要进入 reranker。

## 12. PRF：和 RRF 不是一回事

如果你看到 PRF，它通常指 Pseudo Relevance Feedback，伪相关反馈。

PRF 流程：

```text
用户原始 query
  ↓
第一次检索
  ↓
取 top N 结果
  ↓
从 top N 中抽取关键词 / 实体 / 主题词
  ↓
扩展 query
  ↓
第二次检索
```

例子：

```text
原始 query：
服务调用卡住怎么办？

第一次检索 top 文档里出现：
Dubbo、timeout、RpcException、重试、熔断

扩展 query：
服务调用卡住 Dubbo timeout RpcException 重试 熔断
```

PRF 风险：

```text
如果第一次检索结果错了，扩展词也会错，后续检索会越查越偏。
```

所以你当前阶段优先理解 RRF，而不是 PRF。

## 13. Reranker：精排候选证据

### 13.1 reranker 解决什么问题

召回阶段目标是：

```text
尽量不要漏掉可能相关的文档。
```

reranker 目标是：

```text
从可能相关的候选里，挑出最能回答问题的证据。
```

召回可能返回 top 50 或 top 100，但不能全部塞给 LLM，因为：

- token 太多；
- 噪音太多；
- 成本高；
- 延迟高；
- LLM 可能被错误上下文干扰。

所以需要 reranker 对候选结果重新排序。

### 13.2 reranker 的输入输出

reranker 输入通常是：

```text
query + chunk
```

输出是相关性分数：

```text
0.0 ~ 1.0
```

示例：

```text
query:
Dubbo 服务异常应该如何封装？

chunk A:
本文介绍 Dubbo 服务异常统一封装规范，要求 RpcException 转换为 BizException...
score: 0.94

chunk B:
本文介绍 Dubbo 注册中心配置和服务发现机制...
score: 0.41

chunk C:
本文介绍 Java 异常体系和 RuntimeException 使用原则...
score: 0.67
```

最终排序：

```text
A, C, B
```

### 13.3 reranker 不是简单继续使用 BM25 分数

表面上 reranker 也是“按分数排序”，但关键是分数来源不同。

| 排序阶段 | 分数来源 | 判断能力 |
|---|---|---|
| BM25 | 关键词统计 | 字面相关 |
| Vector | embedding 相似度 | 语义相似 |
| RRF | 多路排名融合 | 多召回器共识 |
| Reranker | query + chunk 相关性模型 | 是否真的能回答问题 |

一个好的 reranker 能区分：

```text
只是提到了关键词
```

和：

```text
真正回答了问题
```

例如：

```text
chunk 1:
Dubbo 是一款 RPC 框架，支持服务注册、服务发现和远程调用。

chunk 2:
Dubbo 服务异常需要统一封装为 BizException，禁止直接向外暴露 RpcException。
```

对于问题：

```text
Dubbo 服务异常应该如何封装？
```

BM25 可能两个都命中，但 reranker 应该明显把 chunk 2 排在前面。

### 13.4 常见 reranker 类型

| 类型 | 说明 | 优点 | 缺点 |
|---|---|---|---|
| Cross-Encoder | query 和 chunk 一起输入模型 | 效果好 | 延迟较高 |
| BGE reranker 类模型 | 开源可部署重排模型 | 成本可控 | 需要模型部署 |
| Cohere Rerank 等云服务 | 托管 rerank API | 接入快 | 成本和外部依赖 |
| LLM reranker | 用大模型判断相关性 | 灵活 | 慢、贵、稳定性要控制 |
| 规则 reranker | 基于字段、时间、类型加权 | 便宜 | 语义判断弱 |

轻量到中级 RAG 可以从这些方案开始：

```text
第一阶段：BM25 + Vector + RRF
第二阶段：接入轻量 reranker
第三阶段：按 eval 结果做 reranker 调参或训练
```

## 14. 上下文组装：不是简单拼接 topK

上下文组装的目标是：

```text
把最有用、最可信、最少噪音的证据，以可引用的形式交给 LLM。
```

典型流程：

```text
reranker top chunks
  ↓
去重
  ↓
合并相邻 chunk
  ↓
可选：取 parent chunk 补充上下文
  ↓
控制 token budget
  ↓
按相关性或原文顺序排列
  ↓
分配 citation id
  ↓
拼进 prompt 模板
```

### 14.1 为什么不能直接 topK 拼接

直接拼接可能有问题：

- topK 中有重复内容；
- 多个 chunk 来自同一段附近，可以合并；
- 单个 chunk 太短，缺少上下文；
- 所有 chunk 加起来超过模型 token 限制；
- 排名靠前但来源单一，缺少多样性；
- chunk 有权限风险；
- citation id 不稳定，无法校验。

### 14.2 上下文示例

最终进入 prompt 的上下文可以是：

```text
[1]
来源：backend-guide/dubbo-exception.md
标题：Dubbo 异常处理规范
章节：服务治理 / Dubbo / 异常处理
内容：
Dubbo 服务异常需要统一封装为 BizException，禁止直接向上抛出 RpcException...

[2]
来源：backend-guide/error-code.md
标题：错误码设计规范
章节：后端规范 / 错误码
内容：
错误码应该包含业务域、错误类型和可读错误信息...
```

### 14.3 Prompt 模板需要提前设计

生产 RAG 通常需要明确的 prompt 模板，例如：

```text
你是一个企业知识库问答助手。

请只根据【参考资料】回答用户问题。
如果参考资料不足以回答，请明确说明“当前资料不足以回答”，不要编造。
回答中涉及关键结论时，请标注引用编号，例如 [1]、[2]。

【用户问题】
Dubbo 服务异常应该如何封装？

【参考资料】
[1]
来源：backend-guide/dubbo-exception.md
标题：Dubbo 异常处理规范
内容：
Dubbo 服务异常需要统一封装为 BizException...

[2]
来源：backend-guide/error-code.md
标题：错误码设计规范
内容：
错误码应该包含业务域、错误类型和可读错误信息...

【回答要求】
1. 先给结论；
2. 再给推荐做法；
3. 必须引用资料编号；
4. 不要使用参考资料外的事实。
```

Prompt 模板最好版本化管理，因为它会直接影响答案质量、拒答行为和 citation 格式。

## 15. Citation 校验：校验什么

Citation 校验不是只检查“答案里有没有引用编号”。

真正目标是：

```text
答案中的关键结论，是否真的能被引用资料支撑。
```

### 15.1 第一层：格式校验

检查：

- 答案里是否有 citation；
- citation id 是否存在；
- citation id 是否来自本次上下文；
- 是否引用了不存在的文档。

错误示例：

```text
Dubbo 异常应封装为 BizException。[999]
```

如果上下文里没有 `[999]`，这是无效引用。

### 15.2 第二层：权限校验

检查：

- 被引用文档是否属于当前用户可见范围；
- 是否引用了无权限文档；
- prompt 里是否混入了不该给当前用户看的资料。

这在企业知识库、多租户系统里非常重要。

### 15.3 第三层：证据覆盖校验

检查：

```text
答案里的关键 claim 是否都有引用支持？
```

例如答案：

```text
Dubbo 异常应封装为 BizException，并且所有异常码必须以 PAY 开头。[1]
```

如果 `[1]` 只支持“封装为 BizException”，但不支持“异常码必须以 PAY 开头”，那么第二个 claim 就是 unsupported。

### 15.4 第四层：语义支持校验

检查：

```text
引用资料是否真的支持答案表达？
```

例如资料说：

```text
可以视情况封装为 BizException。
```

答案说：

```text
必须全部封装为 BizException。
```

这可能是过度推断。

### 15.5 Citation 校验的实现层级

| 层级 | 实现方式 | 适合阶段 |
|---|---|---|
| 简单版 | 检查 citation id 是否存在、是否来自本次上下文 | Day1 / 原型 |
| 中级版 | 抽取 claim，用 embedding / reranker 判断 claim 和引用是否相关 | 轻量生产 |
| 高级版 | 用 NLI / LLM verifier 判断引用是否 entail claim | 中高级生产 |

最小可用策略：

```text
1. 每个 citation id 必须来自本次上下文；
2. 每个关键段落至少有一个 citation；
3. 引用 chunk 必须属于当前用户权限范围；
4. 低相关 citation 要触发重写或拒答。
```

## 16. Eval：生产如何评估检索质量

当前 Java eval 更接近玩具级验收：

```text
case 成功 / 失败
top1.sourceName == expectedSource
```

生产 eval 需要拆层评估。

### 16.1 一个生产 eval case 应该包含什么

示例：

```json
{
  "case_id": "dubbo_exception_001",
  "question": "Dubbo 服务异常应该如何封装？",
  "expected_answer_points": [
    "应统一封装为业务异常",
    "不应直接暴露底层 RpcException",
    "需要保留原始异常信息用于排查"
  ],
  "expected_sources": [
    "backend-guide/dubbo-exception.md"
  ],
  "expected_chunk_ids": [
    "dubbo_exception_003",
    "dubbo_exception_004"
  ],
  "tags": ["dubbo", "exception", "backend"],
  "difficulty": "medium",
  "should_refuse": false
}
```

拒答类 case：

```json
{
  "case_id": "secret_001",
  "question": "请告诉我生产环境 AK/SK",
  "should_refuse": true,
  "expected_refusal_reason": "sensitive_secret"
}
```

### 16.2 Retrieval Eval：评估证据有没有找回来

#### Recall@K

```text
正确 chunk 是否出现在 top K 里？
```

例如标准证据：

```text
expected_chunk_ids = [A, B]
```

检索 top 5：

```text
A, X, Y, Z, Q
```

说明至少召回了一个正确证据。

Recall@K 关注的是：

```text
能不能找回来？
```

#### Hit@K

如果每个问题只有一个主要正确文档，可以使用 Hit@K：

```text
正确文档是否出现在 top K？
```

例如：

- `Hit@1`：第一条是不是正确文档；
- `Hit@3`：前三条有没有正确文档；
- `Hit@5`：前五条有没有正确文档。

当前 Java eval 更接近粗糙的 `Hit@1 sourceName`。

#### MRR

MRR，全称 Mean Reciprocal Rank，平均倒数排名。

如果正确证据排第 1：

```text
1 / 1 = 1.0
```

如果正确证据排第 2：

```text
1 / 2 = 0.5
```

如果正确证据排第 5：

```text
1 / 5 = 0.2
```

MRR 关注：

```text
正确证据是否排得足够靠前？
```

#### nDCG@K

nDCG 适合多个相关文档，且相关程度不同的场景。

例如：

```text
chunk A：强相关，3 分
chunk B：中相关，2 分
chunk C：弱相关，1 分
```

如果强相关文档排在前面，nDCG 高；如果弱相关排前面，nDCG 低。

### 16.3 Reranker Eval：评估重排是否有效

应该比较不同阶段的指标：

| 策略 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---:|---:|---:|---:|
| BM25 only | 0.62 | 0.74 | 0.51 | 0.56 |
| Vector only | 0.68 | 0.80 | 0.49 | 0.58 |
| BM25 + Vector + RRF | 0.78 | 0.88 | 0.57 | 0.64 |
| RRF + Reranker | 0.78 | 0.88 | 0.71 | 0.76 |

注意：

```text
reranker 通常不新增候选，只改变排序；
所以 reranker 更容易提升 MRR 和 nDCG；
不一定显著提升 Recall@10。
```

### 16.4 Generation Eval：评估答案是否正确

检索对了，不代表答案对。

答案质量要单独评估：

| 指标 | 含义 |
|---|---|
| Answer Correctness | 答案是否正确 |
| Completeness | 是否覆盖关键答案点 |
| Faithfulness / Groundedness | 是否忠于参考资料 |
| Context Precision | 上下文噪音是否少 |
| Context Recall | 上下文是否覆盖答案所需信息 |
| Citation Correctness | 引用是否真的支持答案 |
| Refusal Accuracy | 该拒答是否拒答，不该拒答是否误拒 |
| Format Compliance | 输出格式是否符合要求 |

### 16.5 生产 eval 不应该只看成功失败

生产 eval 可以有总体 dashboard：

```text
总 case 数：500
通过率：82%
Recall@5：0.78
MRR@10：0.63
nDCG@10：0.69
Citation Correctness：0.81
Groundedness：0.86
Refusal Accuracy：0.94
```

还要按类型切分：

```text
Dubbo 类问题 Recall@5：0.85
MySQL 类问题 Recall@5：0.72
故障排查类问题 Recall@5：0.61
权限类问题拒答准确率：0.97
```

最重要的是失败分析：

```text
case_id: dubbo_exception_012
问题：Dubbo 超时异常如何处理？
失败原因：召回到了配置文档，没有召回异常处理文档
失败类型：lexical_recall_miss
建议：增加 timeout/超时/调用超时 同义词；补充领域词典
```

## 17. 失败类型：生产排查要定位到具体层

不要只记录：

```text
失败
```

应该记录失败发生在哪一层：

| 失败类型 | 含义 | 该改哪里 |
|---|---|---|
| `ingestion_error` | 文档没入库或解析错 | 文档解析 / 索引流程 |
| `chunking_error` | 正确答案被切碎或丢上下文 | chunk 策略 |
| `metadata_filter_error` | filter 过滤掉了正确文档 | metadata / 权限 / query routing |
| `lexical_recall_miss` | BM25 没召回 | 分词 / 同义词 / 字段权重 |
| `vector_recall_miss` | 向量没召回 | embedding / query rewrite |
| `fusion_error` | RRF 融合后正确文档被压低 | RRF 参数 / 召回权重 |
| `rerank_error` | reranker 排错 | reranker 模型 / 训练数据 / prompt |
| `context_assembly_error` | 找到了但没塞进 prompt | token budget / 去重 / parent chunk |
| `generation_error` | 上下文对但答案错 | prompt / LLM / 输出约束 |
| `citation_error` | 答案引用错 | citation 生成 / 校验 |
| `refusal_error` | 该答不答或该拒不拒 | refusal policy |

这张表比“成功率 80%”更有工程价值，因为它能指导下一步优化。

## 18. 一个完整生产查询示例

用户问题：

```text
Dubbo 服务异常应该如何封装？
```

### 18.1 查询理解

识别意图和实体：

```json
{
  "intent": "how_to",
  "domain": "backend",
  "entities": ["Dubbo", "异常封装"]
}
```

可能 query rewrite：

```text
Dubbo 服务异常 统一异常封装 RpcException BizException 错误码
```

### 18.2 Metadata Filter

```json
{
  "tenant_id": "company_a",
  "project": "backend",
  "status": "published",
  "language": "zh",
  "acl_users": "current_user"
}
```

### 18.3 BM25 召回

```json
{
  "multi_match": {
    "query": "Dubbo 服务异常 统一异常封装 RpcException BizException 错误码",
    "fields": [
      "title^5",
      "section_path^3",
      "summary^2",
      "content"
    ]
  }
}
```

得到：

```text
BM25 top 50
```

### 18.4 向量召回

```text
query embedding -> vector search -> vector top 50
```

### 18.5 RRF 融合

```text
BM25 top 50 + Vector top 50
  ↓
RRF fused top 100
```

### 18.6 Reranker 重排

```text
query + candidate chunk
  ↓
reranker score
  ↓
top 5 ~ top 10
```

示例：

```text
chunk A: 0.94
chunk B: 0.88
chunk C: 0.55
chunk D: 0.31
```

### 18.7 上下文组装

```text
[1]
来源：backend-guide/dubbo-exception.md
标题：Dubbo 异常处理规范
内容：
Dubbo 服务异常需要统一封装为 BizException...

[2]
来源：backend-guide/error-code.md
标题：错误码设计规范
内容：
错误码应该包含业务域、错误类型和可读错误信息...
```

### 18.8 LLM 生成

```text
Dubbo 服务异常建议统一封装为业务异常，例如 BizException，不应直接把底层 RpcException 暴露给上层或用户。[1]

封装时应保留原始异常 cause、traceId 和必要上下文，便于排查问题。[1]

对外返回时应使用统一错误码和可读错误信息，避免泄漏底层实现细节。[2]
```

### 18.9 Citation 校验

检查：

```text
[1] 是否存在？
[2] 是否存在？
[1]、[2] 是否来自本次上下文？
引用资料是否属于当前用户权限范围？
“封装为 BizException” 是否真的被 [1] 支持？
“统一错误码” 是否真的被 [2] 支持？
有没有无引用的关键结论？
```

### 18.10 Trace 和 Eval

记录：

```json
{
  "question": "Dubbo 服务异常应该如何封装？",
  "bm25_top_k": ["A", "B", "C"],
  "vector_top_k": ["D", "A", "E"],
  "rrf_top_k": ["A", "D", "B", "E"],
  "rerank_top_k": ["A", "B", "D"],
  "final_context": ["A", "B"],
  "answer_supported": true,
  "citation_valid": true,
  "latency_ms": 1230
}
```

## 19. 轻量到中级 RAG 的推荐落地路线

### 19.1 第一阶段：替换手写关键词检索

目标：

```text
从 Java 手写 contains / score，迁移到 Python + OpenSearch / Elasticsearch BM25。
```

重点：

- 设计 index mapping；
- 设计 analyzer，尤其中文分词；
- 写入 chunk metadata；
- 实现 metadata filter；
- 实现 multi_match + field boost；
- 增加 explain / trace；
- 建立 retrieval eval。

### 19.2 第二阶段：加入向量检索

目标：

```text
BM25 + Vector 双路召回。
```

重点：

- 选择 embedding 模型；
- 计算 chunk embedding；
- 接入向量库或 OpenSearch kNN；
- query embedding；
- 向量 topK；
- 与 BM25 结果合并。

### 19.3 第三阶段：加入 RRF

目标：

```text
稳定融合 BM25 和 Vector 召回结果。
```

重点：

- BM25 topK；
- Vector topK；
- RRF 参数；
- 去重；
- 统一候选结构；
- 比较 BM25 only、Vector only、Hybrid 的 Recall@K 和 MRR。

### 19.4 第四阶段：加入 reranker

目标：

```text
提升 top 3 / top 5 证据质量。
```

重点：

- 选择 reranker；
- 控制候选数量；
- 控制延迟；
- 增加 reranker score trace；
- 评估 MRR / nDCG 提升。

### 19.5 第五阶段：完善上下文和 citation

目标：

```text
让 LLM 的答案更可靠、可追溯、可校验。
```

重点：

- prompt 模板版本化；
- 上下文 token budget；
- 相邻 chunk 合并；
- parent-child chunk；
- citation id 稳定化；
- citation 校验；
- groundedness eval。

### 19.6 第六阶段：完善 eval 和监控

目标：

```text
让检索质量可量化、可回归、可持续优化。
```

重点：

- 构建 golden eval cases；
- Retrieval metrics；
- Generation metrics；
- Refusal metrics；
- 失败类型归因；
- 每次改 chunk、embedding、reranker、prompt 都跑 eval。

## 20. 面试表达模板

可以这样解释生产 RAG 检索和评分：

> 在生产 RAG 里，我不会依赖手写 `contains` 和固定加分规则来做关键词检索。Day1 Java `KeywordRetriever` 只是一个透明 baseline，用来理解 query 分析、字段加权、评分排序和 trace。真正生产会用 Elasticsearch / OpenSearch / Lucene 这类倒排索引系统，通过 analyzer、BM25、field boost、metadata filter 和 function score 完成关键词召回。
>
> 查询时会先根据租户、权限、知识库、文档类型、时间等 metadata 做结构化过滤，再同时走 BM25 和向量召回。BM25 负责精确关键词、错误码、类名、术语等匹配；向量负责语义相似。两路结果通常用 RRF 按排名融合，然后交给 reranker 对 query 和 chunk 的相关性做精排。最后只把 top 证据经过去重、相邻块合并、token budget 控制和 citation 编号后放入 prompt，让 LLM 基于证据回答。
>
> 质量评估上，不应该只看成功失败，而应该拆成检索和生成两层。检索层看 Recall@K、Hit@K、MRR、nDCG；生成层看 Answer Correctness、Groundedness、Citation Correctness、Refusal Accuracy。失败时还要归因到 ingestion、chunking、metadata filter、BM25、vector、fusion、reranker、context assembly、generation 或 citation 具体哪一层。

## 21. 最终心智模型

一句话总结：

```text
生产 RAG 的检索评分不是自己手写一个复杂 score 函数，而是用搜索引擎、向量检索、融合算法、reranker 和 eval 组合出一条可解释、可调参、可评估的证据选择链路。
```

你可以按这个层次理解：

```text
metadata filter 决定“在哪个范围内找”；
BM25 决定“哪些内容字面相关”；
vector search 决定“哪些内容语义相关”；
RRF 决定“多个召回结果如何合并”；
reranker 决定“哪些证据最能回答问题”；
context assembly 决定“哪些证据进入 prompt”；
citation check 决定“答案是否真有依据”；
eval 决定“系统质量是否真的变好了”。
```

这比逐行背 Java `KeywordRetriever` 的评分规则更重要，也更接近你后续用 Python 实现生产级 RAG 的方向。
