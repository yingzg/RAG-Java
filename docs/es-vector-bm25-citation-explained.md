# ES 评分、向量检索、BM25 与 Citation 校验详解

> 适用读者：已经熟悉 Java 后端开发，正在学习 RAG，但还不熟悉搜索引擎和向量检索。
>
> 本文集中回答四个问题：
>
> 1. Elasticsearch 到底如何计算 `_score`，`title^5` 和 `weight: 1.5` 分别是什么意思？
> 2. 向量检索使用哪些框架，完整实现流程是什么？
> 3. BM25 是不是精确检索或倒排索引检索的统称？
> 4. “Citation 必须来自本次上下文”到底在校验什么？

相关的完整生产检索流程见：[RAG 检索与评分设计](./retrieval-scoring-design.md)。

---

## 1. 先记住这 12 个结论

1. Elasticsearch 建索引时不会给“Java”“线程池”等词人工写死一个固定分数。
2. 建索引时主要做分词、建立倒排索引，并保存词频、文档长度等统计信息。
3. 用户查询时，Elasticsearch 才根据 query 和索引统计信息动态计算 `_score`。
4. Elasticsearch 默认常用 BM25 计算文本相关性分数。
5. `title^5` 表示标题字段的查询权重是 5，不是把标题内容预先写成 5 分。
6. `weight: 1.5` 通常是 `function_score` 中的业务权重；它怎样参与总分取决于 `score_mode` 和 `boost_mode`。
7. `_score` 是同一次查询中用于排序的相对分数，不是准确率，也不是概率。
8. ES 自动算分不等于不可控；生产系统通过 analyzer、query、字段权重、过滤条件、业务权重和 eval 控制结果。
9. BM25 是一种文本相关性排名算法，不是倒排索引、精确查询或关键词检索的统称。
10. 向量检索的核心是：文档和问题都转成向量，再按向量距离找语义相近的 chunk。
11. BM25 和向量分数通常不能直接相加，常用 RRF 按排名进行融合。
12. Citation 校验至少分两层：引用编号是否合法，以及引用内容是否真的支持答案。

---

## 2. 先建立完整心智模型

一次生产 RAG 查询大致经过以下步骤：

```text
用户问题
  │
  ├─ 结构化条件：tenant_id、kb_id、权限、文档类型、时间范围
  │
  ├─ BM25 关键词召回 ───────────┐
  │                            │
  └─ Embedding 向量召回 ───────┤
                               ▼
                           RRF 融合
                               │
                               ▼
                          Reranker 精排
                               │
                               ▼
                    上下文组装并分配证据编号
                         S1、S2、S3……
                               │
                               ▼
                         LLM 基于证据回答
                               │
                               ▼
                    Citation 合法性和支持性校验
```

其中，ES 的 `_score` 主要解决的是“在某一路召回中，哪个 chunk 更相关”。它不是整个 RAG 的最终正确率。

---

# 第一部分：Elasticsearch 到底怎样计算分数

## 3. 写入 ES 时发生了什么

假设知识库里有两个 chunk。

### Chunk A

```text
title: Java 线程池参数说明
content: corePoolSize 表示线程池的核心线程数。
```

### Chunk B

```text
title: Java 并发问题排查
content: 当线程池任务堆积时，需要检查 corePoolSize 和队列容量。
```

写入 ES 时，大致会经历以下过程。

### 3.1 Analyzer 分词

Analyzer 可以理解为“文本进入倒排索引前的标准化与切词流水线”。它可能执行：

```text
原始文本
  -> 字符标准化
  -> 分词
  -> 小写转换
  -> 停用词处理
  -> 同义词处理（可选）
  -> token 列表
```

例如：

```text
Java 线程池参数说明
```

经过合适的中文分词器后，可能得到：

```text
java、线程池、参数、说明
```

实际结果由使用的 analyzer 决定。中文检索不能直接假设 ES 默认分词就足够好，生产中通常需要明确配置中文分词策略、词典和同义词。

### 3.2 建立倒排索引

倒排索引记录“一个词出现在哪些文档中”，概念上类似：

```text
线程池       -> Chunk A, Chunk B
corePoolSize -> Chunk A, Chunk B
参数         -> Chunk A
任务堆积     -> Chunk B
```

它的作用是快速寻找候选文档，而不是完整定义最终排名。

### 3.3 保存统计信息

为了查询时计算 BM25，搜索引擎还会保存或推导：

- 某个词在当前文档中出现多少次；
- 某个词在多少篇文档中出现；
- 当前字段的文档长度；
- 当前字段的平均文档长度；
- 整个索引中的文档数量。

因此，写入阶段是在准备“算分所需的数据”，不是给每个词提前写死分数。

---

## 4. 查询时发生了什么

用户查询：

```text
corePoolSize 是什么意思
```

查询文本也会经过 analyzer，形成查询 token，例如：

```text
corePoolSize、意思
```

ES 随后大致完成两件事：

1. 通过倒排索引找到包含这些 token 的候选 chunk；
2. 使用 BM25 等相似度算法为每个候选 chunk 动态计算 `_score`。

返回结果通常类似：

```json
{
  "hits": {
    "hits": [
      {
        "_id": "chunk-a",
        "_score": 8.42,
        "_source": {
          "title": "Java 线程池参数说明"
        }
      },
      {
        "_id": "chunk-b",
        "_score": 5.17,
        "_source": {
          "title": "Java 并发问题排查"
        }
      }
    ]
  }
}
```

这里的 `_score` 是 ES 为本次 query 计算出来的相关性分数。默认按分数从高到低排序。

需要特别注意：

- `8.42` 不代表 84.2% 正确；
- `5.17` 不代表 51.7% 相似；
- 通常只在同一次查询、同一种查询配置下比较排名；
- 不要简单规定“所有查询 `_score > 8` 才算正确”；
- 换一个 query、索引语料或 query DSL，分数范围都可能改变。

---

## 5. BM25 分数是怎样来的

BM25 的完整数学细节暂时不需要背。先理解下面这个简化模型：

```text
某个 chunk 的 BM25 分数
  ≈ query 中每个词对该 chunk 的贡献之和

某个词的贡献
  ≈ 词的稀有程度
    × 词在当前 chunk 中的出现程度
    × 文档长度归一化
```

对应三个核心因素。

### 5.1 IDF：越稀有的词，通常越有区分度

如果知识库里几乎每篇文档都有“Java”，那么“Java”的区分能力不强。

如果只有少数文档出现 `RejectedExecutionHandler`，这个词的区分度很高。

所以一般有：

```text
RejectedExecutionHandler 的 IDF > Java 的 IDF
```

这符合人的直觉：用户明确搜索一个少见的类名时，包含这个类名的文档应该优先。

### 5.2 TF：词在当前 chunk 中出现，能证明相关性

某个查询词在 chunk 中出现多次，通常说明 chunk 与它更相关。

但 BM25 不会让词频无限线性增长。一个词从 0 次变成 1 次很重要，从 20 次变成 21 次通常没有那么重要。

这叫词频饱和。

### 5.3 长度归一化：防止长文档天然占便宜

一段 5,000 字的内容更容易偶然包含查询词。如果只计算词频，长文档会天然占优势。

BM25 会结合字段平均长度，对过长文档做一定归一化。

### 5.4 一个常见的 BM25 公式

为了建立概念，可以看下面这个常见形式：

```text
score(D, Q)
  = Σ IDF(qi)
      × [ TF(qi, D) × (k1 + 1) ]
        / [ TF(qi, D) + k1 × (1 - b + b × |D| / avgdl) ]
```

变量含义：

| 变量 | 含义 |
|---|---|
| `D` | 当前文档或 chunk |
| `Q` | 用户查询 |
| `qi` | 查询中的某个词 |
| `TF(qi, D)` | 该词在当前文档中的出现频率 |
| `IDF(qi)` | 该词在整个语料中的稀有程度 |
| `|D|` | 当前字段长度 |
| `avgdl` | 当前字段的平均长度 |
| `k1` | 控制词频饱和速度，Elastic 默认 BM25 常见值为 1.2 |
| `b` | 控制长度归一化强度，Elastic 默认 BM25 常见值为 0.75 |

你不需要在业务代码中手写这个公式。Lucene/Elasticsearch 会计算它。

你真正要掌握的是：哪些输入因素会影响排名，以及如何通过 eval 判断配置是否合理。

---

## 6. `title^5` 到底是什么意思

看一个查询：

```json
{
  "query": {
    "multi_match": {
      "query": "Java 线程池拒绝策略",
      "fields": [
        "title^5",
        "section_path^3",
        "summary^2",
        "content"
      ]
    }
  }
}
```

`title^5` 表示：

```text
title 字段的查询 boost = 5
```

它表达的是业务判断：

```text
如果查询词出现在标题中，通常比只出现在正文某个角落更能说明文档主题相关。
```

它不表示：

```text
标题中的每个词在写入 ES 时固定存成 5 分。
```

也不表示：

```text
只要标题命中，最终总分就一定精确增加 5 分。
```

更合适的理解是：ES 先得到该字段对于当前 query 的相关性贡献，再应用字段 boost。最终组合方式还受查询类型影响。

### 6.1 简化数字示例

为了理解字段权重，先假设某次查询得到以下“字段相关性贡献”。这些数字只用于教学，不等于 ES 的实际内部输出。

#### Chunk A

```text
title         原始相关性 = 1.4
section_path  原始相关性 = 0.8
content       原始相关性 = 2.0
```

如果按非常简化的“各字段贡献相加”理解：

```text
title         1.4 × 5 = 7.0
section_path  0.8 × 3 = 2.4
content       2.0 × 1 = 2.0

简化总贡献 ≈ 11.4
```

#### Chunk B

```text
title         原始相关性 = 0
section_path  原始相关性 = 0.3
content       原始相关性 = 3.0
```

```text
title         0   × 5 = 0
section_path  0.3 × 3 = 0.9
content       3.0 × 1 = 3.0

简化总贡献 ≈ 3.9
```

所以 Chunk A 可能排在 Chunk B 前面，因为标题和章节路径更明确地表明它就是在讲用户的问题。

### 6.2 为什么只能说“简化理解”

`multi_match` 有多种类型，字段分数的组合方式不同。

| 类型 | 直观理解 | 常见用途 |
|---|---|---|
| `best_fields` | 主要采用匹配最好的字段；其他字段可通过 `tie_breaker` 提供部分贡献 | 默认行为，找最能代表相关性的字段 |
| `most_fields` | 更倾向于累计多个字段中的匹配证据 | 同一内容以不同分析方式建立多个字段时常见 |
| `cross_fields` | 将多个字段更像一个逻辑大字段处理 | 查询词可能分散在姓名、标题等多个字段时 |

因此，不能把任意 `multi_match` 都机械理解为：

```text
最终分数 = title 分 × 5 + section 分 × 3 + content 分
```

这个式子适合建立初步直觉，但实际分数必须结合 query 类型，并使用 Explain API 查看。

---

## 7. `weight: 1.5` 又是怎么参与评分的

`weight` 常见于 `function_score` 查询，用来加入 BM25 之外的业务信号。

例如，希望官方文档比个人笔记略微优先：

```json
{
  "query": {
    "function_score": {
      "query": {
        "multi_match": {
          "query": "Java 线程池拒绝策略",
          "fields": ["title^5", "section_path^3", "content"]
        }
      },
      "functions": [
        {
          "filter": {
            "term": {
              "source_type": "official"
            }
          },
          "weight": 1.5
        }
      ],
      "score_mode": "multiply",
      "boost_mode": "multiply"
    }
  }
}
```

这段配置的意图是：

1. 先由内部的 `multi_match` 计算文本相关性分数；
2. 如果文档满足 `source_type = official`，获得权重 1.5；
3. 根据 `score_mode` 组合多个 function；
4. 根据 `boost_mode` 把 function 结果与原 query 分数组合。

### 7.1 `boost_mode` 决定怎样组合原始 query 分和 function 分

假设：

```text
原始 BM25/query score = 8.0
function 计算结果      = 1.5
```

不同 `boost_mode` 的直观结果如下：

| `boost_mode` | 简化计算 | 示例结果 |
|---|---:|---:|
| `multiply` | `queryScore × functionScore` | `8.0 × 1.5 = 12.0` |
| `sum` | `queryScore + functionScore` | `8.0 + 1.5 = 9.5` |
| `replace` | 只使用 function score | `1.5` |
| `max` | 两者取最大值 | `8.0` |
| `min` | 两者取最小值 | `1.5` |
| `avg` | 组合后取平均，具体应以官方定义和 Explain 输出为准 | 不要凭直觉猜 |

`function_score` 默认 `boost_mode` 常用行为是 `multiply`，但生产代码中建议显式写出，避免维护者误解。

### 7.2 `score_mode` 决定多个 function 如何相互组合

如果同时有多个业务函数：

```text
官方来源权重 = 1.5
高质量文档权重 = 1.2
新鲜度衰减函数 = 0.9
```

`score_mode` 决定先如何合成一个 function score：

| `score_mode` | 直观含义 |
|---|---|
| `multiply` | 多个 function 结果相乘 |
| `sum` | 多个 function 结果相加 |
| `avg` | 多个 function 结果取平均或加权平均 |
| `max` | 取最大的 function 结果 |
| `min` | 取最小的 function 结果 |
| `first` | 使用第一个匹配的 function |

然后再由 `boost_mode` 把合成后的 function score 与原 query score 组合。

可以把它记成两层：

```text
多个业务函数
  │
  └─ score_mode ──> functionScore
                         │
原始 queryScore ─────────┤
                         └─ boost_mode ──> 最终 _score
```

### 7.3 业务权重为什么不能设置得太大

假设两个文档：

```text
文档 A：文本相关性 8.0，普通来源，权重 1.0，最终 8.0
文档 B：文本相关性 1.0，官方来源，权重 20，最终 20.0
```

文档 B 明明与问题不相关，却因为业务权重过大排到第一。

因此，生产中通常遵循：

- 先保证文本或语义相关；
- 业务权重只做有限幅度调整；
- 权重不是靠感觉决定，而是用离线 eval 比较；
- 重要过滤条件，例如租户和权限，必须使用 filter，不能用低分降权代替。

---

## 8. ES 自动算分是不是不可控

不是。

更准确的说法是：

```text
单个结果的精确分值不适合人工手算和写死，
但影响相关性的规则、查询结构和验收标准是可控制的。
```

### 8.1 生产中能够控制什么

#### 索引结构

- 哪些字段是 `text`，需要分词检索；
- 哪些字段是 `keyword`，用于精确过滤和聚合；
- 是否为标题、章节、正文分别建字段；
- 是否保留规范化字段、拼音字段、同义词字段；
- chunk 和 metadata 如何映射。

#### Analyzer

- 中文怎样分词；
- 英文是否转小写；
- 类名、方法名、错误码怎样保留；
- 是否使用同义词；
- 是否去除停用词。

#### Query DSL

- 使用 `match`、`multi_match`、`match_phrase` 还是 `term`；
- `must`、`should`、`filter` 怎样组合；
- 字段 boost 多大；
- 是否要求最少命中若干查询词；
- 是否加入 phrase boost。

#### Metadata filter

- 当前租户；
- 当前知识库；
- 用户或角色权限；
- 文档类型；
- 版本和生效时间。

#### 业务排序信号

- 官方来源轻度加权；
- 质量等级；
- 新鲜度衰减；
- 已废弃内容降权。

#### Eval

- Recall@K 是否提高；
- MRR 是否提高；
- nDCG 是否提高；
- 不同问题类型是否出现回归；
- 权限过滤是否始终正确。

### 8.2 不应该追求什么

不应该追求：

```text
让开发者在看到任何文档前，精确预测它一定是 13.427 分。
```

应该追求：

```text
对于标注好的测试问题，正确证据稳定进入 topK，
排名指标达到目标，错误能够通过 trace 和 Explain 定位。
```

这和数据库优化很像。开发者不会人工计算每一个 SQL 的成本估值，但会控制索引、SQL 结构、统计信息，并通过执行计划和压测验证。

### 8.3 如何解释某一个 `_score`

Elasticsearch 提供 Explain API，可以解释一个文档为什么得到当前分数。它能展示：

- 命中了哪些查询词；
- 每个词的 IDF；
- 词频和字段长度怎样影响分数；
- 字段 boost 怎样参与；
- `function_score` 怎样组合。

开发时也可以临时在搜索请求中使用：

```json
{
  "explain": true,
  "query": {
    "multi_match": {
      "query": "Java 线程池拒绝策略",
      "fields": ["title^5", "section_path^3", "content"]
    }
  }
}
```

不要在高流量生产请求中默认对所有结果开启 explain，它主要用于调试和分析，因为会增加计算和响应体开销。

---

## 9. ES 检索不准确时，通常怎样排查

建议按下面的顺序排查，而不是第一反应就改 boost。

### 第一步：检查正确文档是否进入索引

```text
文档解析是否成功？
chunk 是否丢失？
metadata 是否正确？
版本是否写错？
```

### 第二步：检查 metadata filter 是否把正确结果过滤掉

```text
tenant_id 是否正确？
kb_id 是否正确？
ACL 是否正确？
doc_type、version、status 条件是否过严？
```

如果正确证据在 filter 阶段已经被排除，后面分数再好也无法召回。

### 第三步：检查分词

分别查看：

- 文档写入时产生了哪些 token；
- query 查询时产生了哪些 token；
- 类名、方法名、错误码有没有被错误切开；
- 中文复合词有没有切错；
- 查询和索引使用的 analyzer 是否匹配。

### 第四步：检查 query 结构

```text
该用 term 的地方是否误用了 match？
该用 match 的地方是否误用了 term？
must 是否过严？
should 是否没有设置 minimum_should_match？
phrase 条件是否过严？
```

### 第五步：使用 Explain 查看排名原因

比较正确 chunk 和错误 top1 的分数构成。

### 第六步：用 eval 调参

一次修改后，运行整套离线问题集，而不是只观察一个手工 query。否则很容易修好一个问题，同时破坏另外十个问题。

---

# 第二部分：向量检索怎样实现

## 10. 向量检索解决什么问题

BM25 依赖词面匹配。用户和文档使用不同表达时，BM25 可能召回不足。

例如文档写的是：

```text
请求在上游服务长时间无响应后触发读取超时。
```

用户问的是：

```text
为什么接口一直卡住？
```

“卡住”和“读取超时”字面不同，但语义接近。

Embedding 模型会把文本转换成一串浮点数：

```text
"为什么接口一直卡住？"
  -> [0.018, -0.327, 0.104, ..., 0.052]
```

这串数字叫向量。语义越接近的文本，其向量通常越接近。

---

## 11. 向量检索的完整数据流程

### 11.1 文档入库阶段

```text
原始文档
  -> 解析
  -> 切成 chunks
  -> 为每个 chunk 调用 embedding 模型
  -> 得到 chunk vector
  -> 保存 chunk 文本、vector、metadata
```

一个逻辑记录可以表示为：

```json
{
  "chunk_id": "java-thread-pool-001",
  "doc_id": "java-thread-pool",
  "title": "线程池拒绝策略",
  "section_path": "Java / 并发 / 线程池",
  "content": "当工作队列已满并且线程数达到最大值时……",
  "embedding": [0.018, -0.327, 0.104],
  "tenant_id": "personal",
  "kb_id": "java-ai",
  "source_path": "notes/java/thread-pool.md"
}
```

真实 embedding 往往有数百到数千维，示例只写了 3 个数字。

### 11.2 查询阶段

```text
用户问题
  -> 使用同一个 embedding 模型生成 query vector
  -> 在向量索引中寻找最近的 topK chunk vectors
  -> 返回相似 chunk 和距离/相似度
```

通常使用：

- 余弦相似度 cosine similarity；
- 点积 dot product；
- 欧氏距离 L2 distance。

选择哪一种必须与 embedding 模型和向量库配置一致。

### 11.3 为什么要求使用同一个 embedding 模型

不同模型的向量空间不同。下面两个向量即使维度一样，也不能默认直接比较：

```text
文档向量：模型 A 生成
查询向量：模型 B 生成
```

更换 embedding 模型时，通常需要重新生成全部文档向量并重建向量索引。

因此，生产数据应记录：

```text
embedding_model
embedding_model_version
embedding_dimension
embedding_created_at
```

---

## 12. 常见向量检索框架怎么选

| 方案 | 类型 | 优点 | 代价 | 适合阶段 |
|---|---|---|---|---|
| FAISS | 本地向量检索库 | 快、成熟、适合本地实验；不要求部署服务 | metadata、持久化、权限等需要自己补 | 学习、个人本地工具 |
| Chroma | 轻量向量存储 | Python 接入简单，适合快速原型 | 大规模和复杂生产治理能力有限 | 学习、Demo、个人知识库 |
| Qdrant | 专用向量数据库 | 支持 metadata filter、持久化、服务化，接口清晰 | 多一个服务需要部署和运维 | 轻量到中级生产 |
| Milvus | 专用向量数据库 | 面向大规模向量检索，生态较完整 | 组件和运维复杂度相对更高 | 中大型系统 |
| Weaviate | 专用向量数据库 | 提供较完整的语义检索能力 | 引入服务和平台学习成本 | 中级生产 |
| pgvector | PostgreSQL 扩展 | 复用 PostgreSQL，数据和权限管理熟悉 | 极大规模或极致性能场景需谨慎评估 | 已有 PostgreSQL 的轻中型项目 |
| Elasticsearch / OpenSearch | 搜索引擎 + 向量检索 | 同时做 BM25、filter 和 kNN，减少系统种类 | 资源消耗和搜索调优复杂度较高 | 已经使用 ES/OS 的生产系统 |

### 12.1 对你的个人 Java/AI 知识库的建议

第一版不需要同时引入 ES、Milvus、复杂 reranker 和全套平台。

推荐两条路线。

#### 路线 A：学习和快速完成

```text
Python
  + Markdown 解析
  + SQLite 保存文档元数据
  + FAISS 保存/检索向量
  + 简单关键词检索
  + RRF
  + LLM 生成答案
```

优点：依赖少，能够真正理解每一层。

缺点：metadata filter、并发、增量更新等需要补一些代码。

#### 路线 B：更接近轻量生产

```text
Python FastAPI
  + Qdrant
  + Qdrant metadata filter
  + 向量召回
  + 一个轻量 BM25 实现或 OpenSearch 关键词召回
  + RRF
  + LLM
```

如果后面确定使用 Elasticsearch/OpenSearch，则可以让一个引擎同时承担：

```text
metadata filter + BM25 + vector kNN
```

系统组件更少，但 ES 本身的 mapping、analyzer、查询调优需要系统学习。

---

## 13. 一个 Python 风格的向量入库伪代码

下面只展示结构，不绑定某个 SDK：

```python
def index_document(document):
    chunks = chunker.split(document)

    for chunk in chunks:
        vector = embedding_model.embed(chunk.content)

        vector_store.upsert(
            id=chunk.chunk_id,
            vector=vector,
            payload={
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "section_path": chunk.section_path,
                "content": chunk.content,
                "tenant_id": chunk.tenant_id,
                "kb_id": chunk.kb_id,
                "source_path": chunk.source_path,
            },
        )
```

查询伪代码：

```python
def vector_search(query, tenant_id, kb_id, top_k=30):
    query_vector = embedding_model.embed(query)

    return vector_store.search(
        vector=query_vector,
        top_k=top_k,
        filter={
            "tenant_id": tenant_id,
            "kb_id": kb_id,
        },
    )
```

这里的 filter 是结构化过滤，不是对正文做 `contains`。

---

## 14. 向量检索分数能不能直接和 BM25 相加

通常不建议。

原因是两者量纲不同：

```text
BM25 score：可能是 3.2、12.7、28.4
cosine similarity：可能是 0.61、0.78、0.84
```

直接相加会让数值范围更大的那一路天然占优势。

常见做法是 RRF，Reciprocal Rank Fusion，中文可理解为“倒数排名融合”。

公式：

```text
RRFScore(d) = Σ 1 / (k + rank_i(d))
```

它不关心原始分数具体是多少，只关心某个 chunk 在各路结果中排第几。

例如：

```text
Chunk A：BM25 第 1，Vector 第 3
Chunk B：BM25 第 8，Vector 第 1
Chunk C：BM25 第 2，Vector 未召回
```

RRF 会奖励“在多路召回中都靠前”的结果，同时保留只在某一路表现很好的结果。

---

# 第三部分：BM25 到底是什么

## 15. BM25 不是倒排索引的统称

下面几个概念要分开。

| 概念 | 解决的问题 | 示例 |
|---|---|---|
| Analyzer / 分词 | 文本怎样变成 token | “线程池拒绝策略”切成哪些词 |
| 倒排索引 | 哪些文档包含某个 token | `线程池 -> chunk1, chunk7` |
| BM25 | 候选文档按照文本相关性怎样排序 | chunk1 和 chunk7 谁更相关 |
| Term query | 精确查找索引中的 term，不对查询值做全文分词 | `tenant_id = personal` |
| Match query | 对查询文本做分析后执行全文检索 | 搜索“线程池拒绝策略” |
| Phrase query | 要求词按相近位置和顺序出现 | 搜索完整短语 |
| Vector search | 按语义向量距离找相似内容 | “卡住”匹配“读取超时” |

因此，更准确的流程是：

```text
Analyzer 分词
  -> 倒排索引快速找到含查询词的候选文档
  -> BM25 为候选文档计算文本相关性分数
  -> 按分数排序
```

### 15.1 BM25 也不是“精确检索”

精确过滤通常使用 `keyword` 字段配合 `term` query，例如：

```json
{
  "term": {
    "tenant_id": "personal"
  }
}
```

它回答的是：

```text
这个字段的值是否精确等于 personal？
```

通常放在 `bool.filter` 中，不参与相关性评分。

BM25 回答的是：

```text
这个文本与用户查询在词面上有多相关？
```

它通常用于 `text` 字段上的全文检索，并参与 `_score`。

### 15.2 为什么 RAG 里仍然需要 BM25

向量检索并不能替代所有关键词检索。BM25 对下面这些内容通常很重要：

- Java 类名和方法名；
- 错误码；
- Trace ID；
- 配置键；
- 产品型号；
- 版本号；
- 专有名词；
- 用户明确输入的原文短语。

例如：

```text
RejectedExecutionException
spring.main.allow-circular-references
ORA-00060
```

这些查询往往要求字面命中，BM25 或 term/phrase 查询比纯向量检索更可靠。

所以生产 RAG 常见设计是：

```text
BM25 负责“字面上明确相关”
Vector 负责“语义上表达相近”
RRF 负责“融合两路排名”
Reranker 负责“结合完整 query 和 chunk 做精排”
```

---

# 第四部分：Citation 校验到底校验什么

## 16. 什么叫“引用必须来自本次上下文”

假设整个知识库有 100,000 个 chunks：

```text
S1 ... S100000
```

本次用户请求经过召回和 reranker 后，系统只选择 3 个证据放进 LLM prompt：

```text
[S12] ThreadPoolExecutor 参数说明……
[S37] 拒绝策略触发条件……
[S85] CallerRunsPolicy 的行为……
```

那么，本次请求允许引用的 ID 集合就是：

```text
allowedCitationIds = {S12, S37, S85}
```

LLM 回答：

```text
当线程数达到 maximumPoolSize 且队列已满时，会触发拒绝策略。[S37]
CallerRunsPolicy 会让提交任务的线程执行该任务。[S85]
```

这两个引用都来自本次上下文，编号合法。

如果 LLM 回答：

```text
DiscardPolicy 会记录错误日志。[S999]
```

即使 `S999` 确实存在于整个知识库，它没有被放入本次 prompt，也不是本次回答的合法证据。

这就是“Citation 必须来自本次上下文”的含义。

---

## 17. 为什么不能允许引用知识库里的任意 chunk

LLM 在本次生成时只应该依据传给它的证据回答。

如果它引用了一个没有放进 prompt 的 chunk，至少存在一种问题：

- 模型编造了一个看似合法的 ID；
- 服务端把其他请求的证据混进来了；
- citation 映射发生错位；
- prompt 或输出解析存在 bug；
- 模型凭参数记忆作答，却伪装成来自知识库证据。

所以第一层校验非常机械：

```text
answerCitationIds ⊆ allowedCitationIds
```

Java/Python 风格伪代码：

```python
def validate_citation_ids(answer_citation_ids, context_chunks):
    allowed_ids = {chunk.chunk_id for chunk in context_chunks}
    invalid_ids = set(answer_citation_ids) - allowed_ids

    return {
        "valid": len(invalid_ids) == 0,
        "invalid_ids": sorted(invalid_ids),
    }
```

这层校验可以完全确定性实现，不需要 LLM。

---

## 18. 编号合法不代表内容真的被支持

看下面的例子。

上下文：

```text
[S85] CallerRunsPolicy 会在调用者线程中执行被拒绝的任务。
```

回答：

```text
CallerRunsPolicy 会直接丢弃任务。[S85]
```

编号 `S85` 确实来自本次上下文，但引用内容不支持这个结论，甚至与答案相反。

因此 Citation 校验至少要拆成两层。

### 第一层：Citation ID Validity

校验：

- 引用格式是否正确；
- 引用 ID 是否存在；
- ID 是否属于本次上下文；
- 引用 chunk 是否仍在当前租户和用户权限范围内。

这层适合用确定性程序完成。

### 第二层：Citation Support / Entailment

校验：

- 答案中的关键 claim 是什么；
- 每个 claim 引用了哪些证据；
- 引用证据是否真的支持该   ；
- 是否存在关键结论没有引用。

这层涉及语义判断，可按成熟度分级实现。

| 级别 | 实现方式 | 能力和限制 |
|---|---|---|
| L0 | 只检查引用格式 | 只能防止格式错误 |
| L1 | 检查引用 ID 属于本次上下文 | 能防止伪造或错位 ID，但不能判断语义支持 |
| L2 | claim 与引用 chunk 做关键词或 embedding 相似度 | 能发现明显不相关引用，但相似不代表逻辑支持 |
| L3 | 使用 reranker 判断 claim 与证据相关性 | 比简单相似度强，但仍不等于严格事实蕴含 |
| L4 | 使用 NLI 模型或 LLM verifier 判断支持、矛盾、无关 | 能做更细语义判断，但有成本和模型误差 |
| L5 | 对高风险事实增加结构化规则或人工审核 | 适合医疗、法律、财务等高风险领域 |

---

## 19. Citation 的完整处理流程

### 19.1 上下文组装时分配稳定编号

```python
context_chunks = [chunk_a, chunk_b, chunk_c]

evidence = [
    {"citation_id": "S1", "chunk_id": chunk_a.id, "content": chunk_a.content},
    {"citation_id": "S2", "chunk_id": chunk_b.id, "content": chunk_b.content},
    {"citation_id": "S3", "chunk_id": chunk_c.id, "content": chunk_c.content},
]
```

展示给 LLM 的编号可以是短编号 `S1`、`S2`，服务端必须保存它到真实 `chunk_id` 的映射。

### 19.2 Prompt 明确回答约束

```text
你只能根据“参考资料”回答。
每个关键结论后必须标注支持该结论的资料编号，例如 [S1]。
只能引用本次提供的资料编号。
资料不足时明确说明无法从现有资料确认，不得编造。
```

Prompt 能降低错误概率，但不能替代服务端校验。

### 19.3 解析回答中的引用

例如从下面文本中提取：

```text
核心线程数由 corePoolSize 控制。[S1] 队列已满后可能创建非核心线程。[S2]
```

得到：

```json
["S1", "S2"]
```

### 19.4 校验引用编号白名单

```text
answer IDs = {S1, S2}
allowed IDs = {S1, S2, S3}

answer IDs 是 allowed IDs 的子集，编号合法。
```

### 19.5 抽取 claim 并检查证据支持

```text
Claim 1：核心线程数由 corePoolSize 控制。
引用：S1

Claim 2：队列已满后可能创建非核心线程。
引用：S2
```

分别判断 S1、S2 是否支持对应 claim。

### 19.6 返回可追溯结果

API 不应只返回答案字符串，还应返回：

```json
{
  "answer": "核心线程数由 corePoolSize 控制。[S1]",
  "citations": [
    {
      "citation_id": "S1",
      "chunk_id": "java-thread-pool-001",
      "source_path": "notes/java/thread-pool.md",
      "section_path": "Java / 并发 / 线程池 / 参数",
      "quote": "corePoolSize 表示线程池保留的核心线程数量。"
    }
  ],
  "citation_validation": {
    "all_ids_allowed": true,
    "all_key_claims_cited": true,
    "all_claims_supported": true
  }
}
```

前端随后可以把 `[S1]` 渲染成可点击来源，而不是只显示一个无法追踪的编号。

---

## 20. “本次上下文”到底是哪一批 chunk

这一点非常容易混淆。

假设检索流水线如下：

```text
BM25 top 50
Vector top 50
  -> RRF 合并后 60 个候选
  -> reranker 选出 top 10
  -> 去重、token budget 控制后只放入 prompt 4 个
```

那么：

```text
本次上下文 = 最终实际放进 LLM prompt 的 4 个证据
```

不是：

- 整个知识库；
- BM25 top 50；
- Vector top 50；
- RRF 后全部候选；
- reranker top 10 中没有进入 prompt 的其他 chunk。

因为只有最终的 4 个证据是模型在本次回答中实际可依据的外部资料。

---

# 第五部分：把四个问题串成一条生产流程

## 21. 一个完整查询示例

用户问题：

```text
Java 线程池什么时候触发 CallerRunsPolicy？
```

### 21.1 Metadata filter

```json
{
  "tenant_id": "personal",
  "kb_id": "java-ai",
  "status": "active"
}
```

这些条件是结构化精确过滤，不使用正文 `contains`，通常也不参与 `_score`。

### 21.2 BM25 召回

查询标题、章节路径和正文：

```json
{
  "multi_match": {
    "query": "Java 线程池什么时候触发 CallerRunsPolicy",
    "fields": ["title^5", "section_path^3", "content"]
  }
}
```

ES 根据词频、词的稀有程度、字段长度、字段 boost 等计算 `_score`，得到 BM25 top 50。

### 21.3 向量召回

把问题转成 query embedding，执行 kNN，得到语义相近的 top 50。

### 21.4 RRF 融合

按两路结果的排名计算 RRF 分数，避免直接相加不同量纲的原始分数。

### 21.5 Reranker

对 `query + candidate chunk` 成对判断相关性，从融合候选中选出 top 8。

Reranker 不是把 BM25 分数重新从大到小排一次，而是使用另一个更精细的模型重新判断 query 与完整 chunk 是否匹配。

### 21.6 上下文组装

系统最终选择 3 个 chunk，分配编号：

```text
[S1] 拒绝策略触发条件……
[S2] CallerRunsPolicy 行为……
[S3] ThreadPoolExecutor.execute 流程……
```

### 21.7 LLM 回答

```text
当线程池无法接收新任务时会执行配置的拒绝策略，例如线程数达到
maximumPoolSize 且工作队列已满。[S1][S3]

如果配置的是 CallerRunsPolicy，被拒绝的任务会由调用 execute 的线程执行；
在线程池已关闭时，该策略不会执行任务。[S2]
```

### 21.8 Citation 校验

服务端检查：

1. 回答只引用了 `S1`、`S2`、`S3`；
2. 这些编号都属于本次 prompt；
3. 它们映射到当前用户有权限访问的 chunk；
4. 每个关键 claim 有引用；
5. 引用内容确实支持对应 claim。

### 21.9 Trace 和 eval

记录：

- metadata filter；
- BM25 topK 和 `_score`；
- vector topK 和相似度；
- RRF 排名；
- reranker 分数；
- 最终上下文 ID；
- LLM 答案；
- citation 校验结果。

离线 eval 再判断正确证据是否进入 Recall@K、首个正确证据排名、答案忠实度和引用正确性。

---

## 22. 你现在需要掌握到什么程度

作为十年 Java 后端程序员，你不需要：

- 手写 Lucene 的 BM25 实现；
- 手算每条 ES 结果的精确 `_score`；
- 从零实现 HNSW 或其他 ANN 向量索引算法；
- 第一版就实现 NLI 级 citation verifier；
- 记住所有 `function_score` 组合模式的数学细节。

你需要能够做到：

1. 清楚区分 analyzer、倒排索引、BM25、term filter 和 vector search；
2. 能解释索引阶段保存统计信息，查询阶段动态算分；
3. 能看懂 `title^5`、`function_score`、`score_mode`、`boost_mode`；
4. 能用 Explain API 排查一个文档为什么排在前面；
5. 能搭建 `BM25 + Vector + RRF` 的最小闭环；
6. 能设计本次上下文的 citation ID 白名单；
7. 能用 Recall@K、MRR、Citation Correctness 等 eval 指标验证调参；
8. 能说明轻量版本和生产增强版之间的取舍。

这已经足够支撑个人知识库实现、面试讲解和后续生产化升级。

---

## 23. 推荐的实践顺序

不要一开始同时实现所有组件。按下面顺序可以保证每一步都可验证。

### 第一步：只做 BM25

- 准备 30 到 100 篇 Java/AI Markdown 笔记；
- 建立 title、section_path、content 和 metadata 字段；
- 配置中文和代码符号的 analyzer；
- 使用 `multi_match` 检索；
- 返回 `_score` 和命中来源；
- 用 Explain 查看 3 到 5 个典型问题。

### 第二步：建立 eval cases

每条 case 至少包含：

```json
{
  "query": "线程池什么时候触发拒绝策略",
  "relevant_chunk_ids": ["thread-pool-reject-001"],
  "expected_source": "notes/java/thread-pool.md"
}
```

先测 Recall@5 和 MRR，不要只凭肉眼判断结果“看起来不错”。

### 第三步：加入向量召回

- 选择 embedding 模型；
- 保存模型名和版本；
- 为所有 chunk 生成 embedding；
- 实现 query embedding 和 vector topK；
- 分别比较 BM25 only、Vector only。

### 第四步：加入 RRF

融合 BM25 与 Vector 的排名，比较 Hybrid 与单路检索的 Recall@K 和 MRR。

### 第五步：接入 LLM 和 Citation L1

- 给最终上下文分配 `S1...Sn`；
- Prompt 要求逐条引用；
- 服务端校验回答中的 ID 必须属于本次上下文；
- API 返回 citation 到真实文件和章节的映射。

### 第六步：根据 eval 决定是否加入 reranker

只有当融合召回已经能找回正确证据，但 top 排名和上下文噪音仍明显有问题时，再加入 reranker。

### 第七步：升级 Citation 支持性校验

先从关键 claim 覆盖率和简单相关性检查做起，再根据风险与错误率决定是否引入 NLI 或 LLM verifier。

---

## 24. 常见误解对照表

| 误解 | 正确理解 |
|---|---|
| 写 ES 时要给每个分词人工设定固定分数 | 写入时建立 token、倒排索引和统计信息，查询时动态算分 |
| `title^5` 是标题命中固定加 5 分 | 它是标题字段的查询 boost，实际分数还受 BM25 和 query 类型影响 |
| `weight: 1.5` 一定是最终分数加 1.5 | 怎样组合取决于 `score_mode` 和 `boost_mode` |
| `_score = 0.8` 就是 80% 正确 | `_score` 是排序相关性值，不是概率 |
| ES 自动算分所以完全不可控 | 规则、索引、query、权重、过滤和 eval 都可控；精确数值由引擎动态计算 |
| BM25 就是倒排索引 | 倒排索引找候选，BM25对文本候选进行相关性排名 |
| BM25 就是精确匹配 | 精确过滤更接近 keyword + term；BM25 是全文文本排名算法 |
| 有向量检索后不需要 BM25 | 类名、错误码、配置键、术语等仍依赖强词面检索 |
| BM25 分和向量相似度直接相加即可 | 两者量纲不同，常用 RRF 做排名融合 |
| reranker 就是再按原分数排序 | reranker 使用更强模型重新评估 query 与 chunk 的相关性 |
| 引用 ID 存在于知识库就合法 | 它必须属于最终实际传给本次 LLM 的上下文 |
| 引用编号合法就说明答案有依据 | 还必须检查引用内容是否真正支持对应 claim |

---

## 25. 面试表达模板

可以用下面这段话概括：

> 在 RAG 的关键词检索中，文档写入 Elasticsearch 时主要完成分词、倒排索引构建和统计信息保存，并不会给每个词人工写死分数。查询时，Elasticsearch 通常使用 BM25，根据词频、逆文档频率和文档长度归一化动态计算 `_score`。`title^5` 是字段级查询 boost，表示标题命中更重要；`function_score` 的 `weight` 用于叠加来源质量、新鲜度等业务信号，最终如何组合由 `score_mode` 和 `boost_mode` 决定。`_score` 是同一次查询内的相对排名分，不是概率，效果要通过 Recall@K、MRR 和 nDCG 等 eval 指标验证。
>
> 为了补足关键词检索对同义表达的不足，我会同时做向量召回。文档 chunk 和 query 使用同一个 embedding 模型转成向量，通过向量库或 Elasticsearch/OpenSearch kNN 找到语义相近结果。BM25 分与向量相似度量纲不同，通常用 RRF 按排名融合，再使用 reranker 精排。
>
> 最终进入 LLM prompt 的证据会分配稳定 citation ID。服务端先校验答案引用的 ID 必须属于本次实际上下文，再进一步校验关键 claim 是否有引用，以及引用内容是否真的支持 claim。这样可以区分“引用编号合法”和“答案确实有证据支持”两个不同问题。

---

## 26. 官方参考资料

- [Elastic：Similarity module 与 BM25 配置](https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity)
- [Elastic：Multi-match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-multi-match-query)
- [Elastic：Function score query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-function-score-query)
- [Elastic：Explain API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-explain)
- [Elastic：kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)
- [FAISS 官方文档](https://faiss.ai/)
- [Qdrant 官方概览](https://qdrant.tech/documentation/overview/)

