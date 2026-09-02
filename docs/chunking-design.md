# RAG 切块设计：从当前 MarkdownChunker 到生产级实现

## 1. 文档目的

本文总结当前 Java `MarkdownChunker` 的切块流程、短块回并行为和已知风险，并给出生产级 RAG 切块的设计方案与自动化测试体系。

适用场景：

- 理解 DAY1 Java 原型当前到底如何切块；
- 将切块能力迁移到 Python 时确定哪些行为需要保留、哪些需要替换；
- 设计轻量到中级生产 RAG 的切块模块；
- 面试时清楚说明切块策略、权衡和质量验证方法。

相关材料：

- 当前实现：`prototype-cli/src/main/java/com/example/rag/document/MarkdownChunker.java`
- 逐行学习笔记：`docs/learning/day1/03-markdown-chunker.md`
- Chunk 数据结构：`prototype-cli/src/main/java/com/example/rag/document/DocumentChunk.java`

## 2. 先记住六句话

1. **先解析文档结构，再处理长度。** 标题、段落、列表、代码块和表格是语义边界。
2. **标题和正文通常属于同一个语义章节。** 标题既可以进入 chunk 内容，也应进入结构化 metadata。
3. **小块用于精准检索，大块用于完整回答。** 生产中常用 parent-child 或相邻块扩展。
4. **不能破坏原子结构。** 代码块、表格、列表、公式不应该被普通字符切分随意截断。
5. **切块不是一次字符串处理。** 它还需要稳定 ID、位置、父子关系、版本和可追溯 metadata。
6. **策略好坏必须由自动化测试和检索 eval 判断。** 平均块长度正常，不代表问答效果正常。

## 3. 当前 MarkdownChunker 的简单流程

当前实现可以简化成四步：

```text
完整 Markdown 文档
  ↓
第一步：按 Markdown 标题切成 Section
  ↓
第二步：Section 超过 1200 字符时，优先按空行段落继续拆
  ↓
第三步：单段仍超过 1200 字符时，每 1200 字符硬切
  ↓
第四步：小于 120 字符的 part，尝试合并到前一个 chunk
  ↓
补充 source、path、sectionPath、chunkIndex、chunkId 等 metadata
  ↓
输出 List<DocumentChunk>
```

对应的两个阈值是：

```java
MAX_CHUNK_CHARS = 1200;
MIN_CHUNK_CHARS = 120;
```

这两个值只是 DAY1 原型的经验参数，不是 RAG 的固定标准。生产实现通常按目标 embedding 模型的 tokenizer 计算 token，而不是直接使用 Java 字符数。

## 4. 第一步：按标题切 Section

假设原文是：

```markdown
# Dubbo 治理

Dubbo 治理的总体说明。

## 超时

超时配置和处理原则。

## 重试

重试配置和幂等性要求。
```

当前实现先得到三个 Section：

| Section | `sectionPath` | `content` 的开头 |
|---|---|---|
| 1 | `Dubbo 治理` | `# Dubbo 治理` |
| 2 | `Dubbo 治理 > 超时` | `## 超时` |
| 3 | `Dubbo 治理 > 重试` | `## 重试` |

### 4.1 标题和正文是不是分开的块

在当前实现中，**标题和正文不是先分别生成两个 chunk**。

遇到标题时，代码会：

1. 结束并保存上一个 Section；
2. 更新标题层级路径；
3. 把标题原文写入新 Section 的 `content`；
4. 后面的正文继续写入这个 Section。

因此，一个普通 Section 的实际内容类似：

```text
## 超时

超时配置和处理原则。
```

标题信息保存了两份：

- 标题原文在 `content` 中，参与检索和回答；
- 标题层级在 `sectionPath` 中，参与过滤、加权、引用和定位。

这种适度冗余是合理的。只保存正文会丢失上下文；只把标题放进 metadata，又可能让不读取 metadata 的 embedding 或检索链路看不到标题语义。

### 4.2 Section 和 Chunk 的关系

Section 是按文档结构得到的语义章节，Chunk 是最终进入索引的检索单元。

二者不是固定的一对一关系：

```text
短 Section       -> 通常生成 1 个 Chunk
超长 Section     -> 生成多个 Chunk
极短 Section     -> 当前实现可能与前一个 Chunk 回并
```

## 5. 第二步：超长 Section 如何继续拆分

如果整个 Section 不超过 1200 字符，直接保留。

如果超过 1200 字符，当前实现先按空行划分段落，再按顺序把段落装入 chunk：

```text
段落 A：500 字符
段落 B：400 字符
段落 C：500 字符
```

执行过程：

```text
A + B = 900，未超过 1200，放在同一 part
A + B + C = 1400，超过 1200
因此输出：
  part 1 = A + B
  part 2 = C
```

这种做法的核心是：能在段落边界切，就不从句子中间硬切。

### 5.1 单个段落自己就超长

如果某个段落本身超过 1200 字符，当前实现按字符位置切：

```text
0～1199
1200～2399
2400～结尾
```

这是保证原型能运行的 fallback，但不适合作为生产默认策略，因为它可能：

- 从句子中间切开；
- 从代码标识符中间切开；
- 破坏 Markdown 代码围栏；
- 拆散表头和表格数据行；
- 把一个列表项切成两个无上下文片段；
- 在切分边界两侧不保留任何 overlap。

## 6. 第三步：短块到底如何回并

### 6.1 “回并”的准确含义

回并不是把当前短内容追加到已经存在的不可变 `DocumentChunk` 对象上。当前代码的真实过程是：

1. 发现当前 part 小于 120 字符；
2. 从最终 `chunks` 列表中删除最后一个 chunk；
3. 取出前一个 chunk 的正文；
4. 拼接“前块正文 + 两个换行 + 当前短正文”；
5. 把 `chunkIndex` 回退到前一个 chunk 的序号；
6. 用拼接后的正文重新创建一个 `DocumentChunk`；
7. 新对象替代被删除的前块。

伪代码：

```text
if 当前 part 长度 < 120 and 已经存在前块:
    previous = 删除最后一个 chunk
    mergedContent = previous.content + "\n\n" + current.content
    currentIndex = previous.chunkIndex
    创建一个新的 chunk(currentIndex, mergedContent)
else:
    正常创建新 chunk
```

### 6.2 同一 Section 内的回并示例

假设一个超长 Section 被拆成：

```text
part 1：900 字符
part 2：80 字符
```

处理 `part 1` 后：

```text
chunks = [chunk(index=0, content=900 字符)]
```

处理 `part 2` 时，因为 80 小于 120：

```text
删除 index=0 的旧 chunk
合并 content = 900 字符 + 两个换行 + 80 字符
重新创建 index=0 的 chunk
```

最终不是两个块，而是一个约 982 字符的块。

### 6.3 当前实现会跨 Section 回并

当前判断条件只检查：

```text
当前内容是否小于 120
最终列表中是否存在前块
```

它**没有检查前块与当前短块是否属于同一个 Section**。

例如：

```markdown
## 超时

超时正文 900 字符。

## 重试

禁止非幂等接口自动重试。
```

假设“重试”Section 只有 50 字符，当前代码可能得到：

```text
content:
  ## 超时
  超时正文……

  ## 重试
  禁止非幂等接口自动重试。

sectionPath:
  Dubbo 治理 > 重试
```

这里产生了 metadata 错配：正文同时包含“超时”和“重试”，但 `sectionPath` 只标记为“重试”。

因此，“短内容会回并”这句话需要加一个重要限定：

> 当前原型是向最终列表中的全局前块回并，不保证同章节。这是需要测试暴露并在生产版修正的已知问题。

### 6.4 回并后可能重新超长

假设：

```text
前块：1180 字符
当前短块：100 字符
```

回并后约为 1282 字符，已经超过 1200。当前主流程不会再次执行超长拆分，因此 `MAX_CHUNK_CHARS` 不是最终输出的严格上限。

### 6.5 标题可能意外成为单独 part

标题和正文正常情况下属于同一个 Section，但如果：

- 整个 Section 超过 1200；
- 标题与正文之间存在空行；
- 正文是一个超过 1200 字符的大段落；

按空行拆段时，标题可能先进入缓冲区。处理超长正文前，标题缓冲区被单独输出；大段正文再被字符硬切。

于是可能出现：

```text
part 1：只有标题
part 2：正文第 1 段硬切结果
part 3：正文第 2 段硬切结果
```

这不是有意设计的“标题块 + 正文块”，而是当前控制流程产生的边界行为。

## 7. 当前实现的完整执行示例

输入：

```markdown
# Dubbo 治理

简介，约 80 字符。

## 超时

正文 A，约 700 字符。

正文 B，约 600 字符。

## 重试

禁止非幂等接口自动重试，约 50 字符。
```

执行过程：

1. 按标题得到三个 Section：
   - `Dubbo 治理`
   - `Dubbo 治理 > 超时`
   - `Dubbo 治理 > 重试`
2. “简介”Section 小于 120，但它是第一个块，没有前块，因此保留。
3. “超时”Section 总长度超过 1200，按空行段落拆成约 700 和 600 字符两个 part。
4. 700 和 600 都不小于 120，各自生成 chunk。
5. “重试”Section 约 50 字符，小于 120，并且已有前块，触发回并。
6. 最后一个“超时”chunk 被删除，其内容与“重试”内容拼接。
7. 新 chunk 复用被删除块的 `chunkIndex`，但使用当前“重试”Section 的 `sectionPath`。

这个例子同时说明三件事：

- 标题和正文默认属于同一个 Section；
- 超长正文会在 Section 内继续拆分；
- 当前回并可能跨标题边界，破坏内容和 metadata 的一致性。

## 8. 为什么生产切块比当前实现复杂

生产切块需要同时满足多个相互冲突的目标：

| 目标 | 块过小时的问题 | 块过大时的问题 |
|---|---|---|
| 检索精准度 | 语义残缺、缺少上下文 | 一个块混入多个主题，向量表达模糊 |
| 答案完整度 | 找到事实但无法解释 | 上下文噪声多，模型可能抓错重点 |
| token 成本 | 可能需要召回很多邻块 | 单块成本高，挤占 prompt 预算 |
| 引用质量 | 引用过碎，用户难阅读 | 引用范围过宽，难证明具体结论 |
| 更新与增量索引 | 块数量多、管理复杂 | 任意小改动可能让大块整体失效 |

所以生产设计不应只问“每块设多少字符”，而应问：

```text
文档是什么类型？
它有哪些不可破坏的结构？
检索使用多大粒度？
回答需要多大上下文？
如何定位回原文？
如何证明新策略优于旧策略？
```

## 9. 常见生产切块策略

### 9.1 固定 token + overlap

按固定 token 数切分，相邻块重复一部分内容。

```text
chunk 1: token 0～499
chunk 2: token 450～949
chunk 3: token 900～1399
```

适合：无明显结构的纯文本、快速 baseline。

优点：简单、大小可预测、容易批量处理。

缺点：可能破坏语义结构；overlap 会增加索引量和重复召回。

### 9.2 递归切分

按优先级逐级尝试边界：

```text
标题 -> 空行 -> 换行 -> 句号 -> 标点 -> token fallback
```

适合：通用文本和 Markdown baseline。

优点：比固定长度更尊重语义边界，同时能保证大小上限。

缺点：仍然不真正理解表格、代码和领域结构。

### 9.3 结构感知切分

先用 Markdown/HTML/PDF/Office parser 建立抽象语法树或结构块，再按结构切分。

可识别：

- 标题层级；
- 段落；
- 列表；
- 代码围栏；
- 表格；
- 引用块；
- 图片及说明；
- 页码和版面区域。

适合：技术文档、产品手册、规章制度。

优点：结构稳定、metadata 丰富、引用定位清楚。

缺点：解析器和异常文档处理成本更高。

### 9.4 语义切分

将句子或段落转换为 embedding，检测相邻内容语义变化较大的位置，在主题变化处切分。

适合：没有可靠标题、长篇叙述、会议纪要。

优点：可能发现作者未显式标记的主题边界。

缺点：切块本身需要模型计算；阈值难调；结果受 embedding 模型影响；可解释性较弱。

### 9.5 Parent-Child / Small-to-Big

同一内容保存两种粒度：

```text
父块：完整章节，负责回答上下文
  ├── 子块 1：小段落，负责精准检索
  ├── 子块 2：小段落，负责精准检索
  └── 子块 3：小段落，负责精准检索
```

检索时搜索子块；命中后把父块或相邻子块扩展进回答上下文。

适合：技术文档、制度文档、需要解释完整性的场景。

优点：兼顾精准召回和完整上下文，是轻量到中级生产 RAG 的优先方案。

缺点：需要维护父子关系、去重、上下文扩展和 token budget。

### 9.6 Sentence Window

索引单句或短句组，命中后附带前后若干句。

适合：事实密集型文本、客服知识、短问短答。

优点：检索粒度细，补充上下文直接。

缺点：窗口大小固定时仍可能跨主题；文档结构利用不足。

### 9.7 多粒度切块

同时索引章节、段落、句子摘要等多个粒度，再进行融合、去重或 rerank。

适合：问题类型差异大、既有概览问题又有细节问题的知识库。

优点：对不同问题粒度更有适应性。

缺点：索引量、召回融合、去重和评估复杂度明显增加。

### 9.8 命题或原子事实切分

把复合段落转换为多个可独立判断的事实单元，例如：

```text
Dubbo 默认超时时间是……
非幂等接口不应自动重试。
异常需要转换为统一错误码。
```

适合：事实问答、知识图谱增强、合规规则检索。

优点：检索精确，适合判断单一事实。

缺点：通常依赖模型抽取；可能丢失上下文；需要保存事实与原文证据的映射。

### 9.9 文档类型专用切分

生产中通常不能让所有文档共用一套规则：

| 文档类型 | 推荐边界 |
|---|---|
| Markdown 技术文档 | 标题、段落、代码块、表格、列表 |
| Java/Python 源码 | 类、方法、函数、注释、调用关系 |
| API 文档 | endpoint、请求、响应、错误码、示例 |
| FAQ | 一个问题和对应答案作为原子单元 |
| 规章制度 | 章、节、条、款、项，保留层级和生效信息 |
| PDF 手册 | 页、标题、版面区域、表格、页眉页脚清理 |
| 表格数据 | 表头和相关数据行共同保留，必要时转为行级事实 |
| 对话记录 | 会话轮次、说话人、时间窗口、主题段 |

## 10. 本项目推荐的生产级切块方案

针对本项目的 Java 技术文档知识库，推荐从“结构感知 + parent-child + token-aware”开始，不必第一版就使用语义切分。

### 10.1 总体流程

```text
原始文档
  ↓
文档类型识别
  ↓
对应 parser 解析为结构化节点
  ↓
清洗导航、页眉页脚、重复内容等噪声
  ↓
构建 Section 层级和不可破坏的原子块
  ↓
生成父块 Parent Chunk
  ↓
在父块内部生成检索子块 Child Chunk
  ↓
补充标题上下文、位置、父子关系、版本、hash
  ↓
按 embedding 模型 tokenizer 校验大小
  ↓
写入索引并运行结构测试与检索 eval
```

### 10.2 原子块规则

先把文档解析成不能随意从中间切开的原子块：

- 普通段落：尽量按句子边界切；
- 代码块：保持围栏和完整语法单元；超长时按类、方法或语句块切；
- 表格：表头随每个子表重复，数据行按组切；
- 列表：尽量保留列表标题与完整列表项；
- FAQ：问题与答案不拆开；
- API：请求、响应和错误码与 endpoint 标题关联；
- 图片：图片说明、OCR 文本和来源位置绑定。

### 10.3 父块和子块

建议初始参数仅作为实验起点：

| 对象 | 初始范围 | 用途 |
|---|---:|---|
| Parent Chunk | 800～1500 tokens | 回答上下文、完整引用 |
| Child Chunk | 300～600 tokens | embedding 和精准检索 |
| Child overlap | 50～100 tokens | 缓解段落边界信息断裂 |

这些数字不能直接当最终答案。应根据真实文档分布、目标模型、top-k、问题类型和 eval 结果调整。

### 10.4 检索后的上下文扩展

```text
查询
  ↓
检索 child chunks
  ↓
融合关键词/向量结果并 rerank
  ↓
按 parentId 去重
  ↓
根据问题和 token budget 选择：
  - 当前 child
  - 前后相邻 child
  - 完整 parent
  ↓
生成回答并引用原文位置
```

这种设计比盲目扩大每个索引块更可控：检索仍然精准，回答时才补充真正需要的上下文。

### 10.5 短块处理规则

生产版不应使用“只要短就并入全局前块”的规则。建议按以下优先级处理：

1. 如果短块与同一 Section 的前一个 child 合并后不超预算，向前合并；
2. 否则如果与同一 Section 的后一个 child 合并后不超预算，向后合并；
3. 标题、提示、警告、FAQ 等独立有意义的短块可以保留；
4. 不跨 Section 合并正文；
5. 必须保留时，通过 parent 标题和相邻上下文增强，而不是篡改结构边界；
6. 每次合并后重新计算 token 数，并校验最终上限。

可以把合并条件写成明确不变量：

```text
sameDocument
AND sameSection
AND structureCompatible
AND mergedTokenCount <= maxTokens
```

## 11. 生产级 Chunk 数据模型

当前 `DocumentChunk` 已有 source、path、sectionPath、index、docType、content 等字段。生产版建议补充：

| 字段 | 作用 |
|---|---|
| `documentId` | 稳定标识原始文档，不依赖本次 chunk 序号 |
| `documentVersion` | 区分文档版本，支持增量索引和回滚 |
| `sectionId` | 稳定标识章节 |
| `parentChunkId` | child 命中后定位父块 |
| `previousChunkId` / `nextChunkId` | 相邻上下文扩展 |
| `headingPath` | 保存完整标题层级 |
| `contentType` | paragraph、code、table、list、faq 等 |
| `startOffset` / `endOffset` | 精确定位原文字符范围 |
| `startLine` / `endLine` | 便于引用和人工排查 |
| `tokenCount` | 按实际 embedding tokenizer 统计 |
| `contentHash` | 内容变更检测、去重、缓存 |
| `chunkerVersion` | 标记切块算法和参数版本 |
| `acl` / `tenantId` | 检索前权限过滤 |
| `language` | 选择 tokenizer、检索器和生成策略 |

稳定 ID 不应只由全局 `chunkIndex` 决定。否则文档开头增加一个段落，后续全部序号漂移，造成大规模无效重建。

## 12. 自动化测试体系

切块测试需要覆盖两个问题：

```text
结构正确性：有没有丢、重、乱、错配、破坏结构？
检索有效性：切完以后，真实问题能不能召回正确证据？
```

二者不能互相替代。单元测试通过，只能证明规则按设计执行；Recall@K 提升，才能证明它对 RAG 任务有效。

### 12.1 第一层：当前 Java baseline 行为刻画测试

在迁移 Python 前，先用测试记录当前 Java 行为。目的不是认可所有行为，而是让迁移变化可见。

建议用例：

| 编号 | 输入 | 断言 |
|---|---|---|
| B01 | 无标题短文档 | 生成一个 chunk，`sectionPath` 为去扩展名文件名 |
| B02 | H1/H2/H3 文档 | 标题层级正确，进入同一 Section 的标题和正文不分离 |
| B03 | H2 切换 | 旧 H3 被清除，不污染新 H2 路径 |
| B04 | 跳级标题 H1→H3 | 当前 baseline 得到跳过空 H2 的路径 |
| B05 | Section 等于 1200 字符 | 不继续拆分 |
| B06 | 多段累计超过 1200 | 优先在空行边界拆分 |
| B07 | 单段超过 1200 | 记录当前字符硬切行为 |
| B08 | 第一个 part 小于 120 | 因无前块而保留 |
| B09 | 同 Section 尾 part 小于 120 | 替换前块并复用前块 index |
| B10 | 新 Section 小于 120 | 暴露当前跨 Section 回并和 metadata 错配 |
| B11 | 1180 + 100 回并 | 暴露回并后超过 1200 的行为 |
| B12 | 超长单段前有标题 | 暴露标题可能成为独立 part 的行为 |

其中 B10～B12 应标为“已知风险测试”。迁移阶段可以先保留；切换生产策略时有意修改断言，不能让行为悄悄变化。

### 12.2 第二层：生产切块规则单元测试

生产实现至少应验证以下不变量。

#### 内容完整性

- 除清洗规则明确删除的内容外，所有原文内容都能映射到至少一个 chunk；
- 去掉设计允许的 overlap 后，正文没有重复也没有遗漏；
- chunk 顺序与原文顺序一致；
- Unicode、中文标点、emoji、CRLF/LF 不造成内容损坏。

#### 大小约束

- 每个 child 的 `tokenCount <= childMaxTokens`；
- 每个 parent 的 `tokenCount <= parentMaxTokens`，或被明确标记为不可拆原子块；
- 合并后重新计算 token，不允许回并绕过上限；
- tokenCount 使用实际 embedding 模型对应的 tokenizer。

#### 结构约束

- 标题层级正确；
- 不跨 Section 合并；
- 代码围栏成对且语言标签保留；
- 表格子块都能关联表头；
- 列表编号和嵌套关系不被破坏；
- FAQ 的问题和答案保持关联；
- 代码块中的 `# comment` 不被当作 Markdown 标题。

#### Metadata 约束

- `documentId/sectionId/parentChunkId` 引用存在且一致；
- start/end offset 或行号能准确定位回原文；
- `contentHash` 与实际 content 一致；
- 相同输入、相同配置、相同 chunkerVersion 产生稳定结果；
- 修改一个 Section 时，不应无故改变其他 Section 的稳定 ID。

### 12.3 第三层：属性测试

属性测试不是只准备几个固定样例，而是随机生成大量标题、段落、长度和 Unicode 组合，验证永远成立的规则。

推荐属性：

```text
任意输入 -> chunker 不抛未处理异常
任意非空有效文档 -> 至少产生一个 chunk
重建正文 -> 与规范化后的原文一致（忽略设计允许的 overlap）
任意 child -> tokenCount 不超过配置上限
任意合并 -> 不跨 documentId 和 sectionId
相同输入运行两次 -> chunk 顺序、ID、metadata 完全一致
```

属性测试尤其适合发现：

- 刚好位于阈值前后的 off-by-one；
- 连续空行；
- 空标题；
- 标题跳级；
- 超长 Unicode 文本；
- CRLF 与 LF 差异；
- 极短尾块连续出现；
- 代码围栏未闭合等异常输入。

### 12.4 第四层：Golden File 回归测试

选取 10～30 个真实文档或经过脱敏的典型片段，固定保存预期 chunk 输出：

```text
fixtures/input/dubbo-timeout.md
fixtures/expected/dubbo-timeout.chunks.json
```

每次修改 parser、tokenizer、阈值或合并策略时，测试展示 chunk diff。评审者可以直接看到：

- 哪些边界移动了；
- 哪些 ID 变化了；
- 哪些 metadata 变化了；
- 是否出现意外的大面积重切。

Golden File 不应只断言整个 JSON 字符串完全相等。可以区分：

- 必须稳定的字段：文档归属、section、位置、关系；
- 允许策略升级后变化的字段：chunkId、tokenCount、边界；
- 需要人工确认的变化：代码块、表格和跨标题边界。

### 12.5 第五层：检索与问答 eval

切块最终服务于检索和回答，因此要建立真实问题集。每条 case 至少包含：

```json
{
  "case_id": "dubbo_retry_001",
  "query": "哪些接口不能自动重试？",
  "expected_document": "dubbo-governance.md",
  "expected_section": "Dubbo 治理 > 重试",
  "expected_evidence": "非幂等接口",
  "question_type": "fact",
  "tags": ["short-section", "boundary"]
}
```

建议指标：

| 指标 | 说明 |
|---|---|
| `Recall@K` | 正确证据是否进入前 K 个候选 |
| `MRR` / `nDCG` | 正确证据排名是否靠前 |
| Evidence Coverage | 回答所需事实是否完整出现在召回上下文 |
| Context Precision | 召回内容中有多少与问题真正相关 |
| Citation Correctness | 引用是否真的支持回答中的结论 |
| Boundary Failure Rate | 正确事实是否因切分边界而丢失 |
| Duplicate Context Ratio | overlap 和多粒度召回造成多少重复上下文 |
| Tokens per Answer | 每次回答最终消耗多少上下文 token |
| Index Size | 不同策略产生多少 chunk 和向量存储量 |
| Ingestion Latency | 文档解析、切块、embedding 和写索引耗时 |

问题集需要覆盖：

- 精确事实问题；
- 跨段落组合问题；
- 需要标题上下文才能理解的问题；
- 代码和配置问题；
- 表格查值问题；
- 概览问题；
- 相邻章节容易混淆的问题；
- 文档中没有答案、应该拒答的问题。

### 12.6 第六层：策略对比实验

不要直接凭感觉选择 `500 tokens + 50 overlap`。用同一套文档和 eval case 对比：

```text
策略 A：固定 500 tokens + 50 overlap
策略 B：结构感知 400 tokens + 80 overlap
策略 C：结构感知 parent-child
策略 D：结构感知 parent-child + rerank
```

每次实验固定其他变量：embedding 模型、索引数据、retriever、top-k、reranker、prompt 和 LLM。否则无法判断指标变化到底来自切块还是其他组件。

建议记录：

```text
chunkerVersion
参数配置
文档集版本
embedding 模型版本
索引版本
eval case 版本
各项指标
失败 case 列表
```

## 13. 必须优先实现的自动化测试清单

如果只安排一到两天，不要一开始追求所有测试框架。按风险优先级实施：

### P0：迁移前必须有

- 标题层级与 `sectionPath`；
- 标题和正文属于同一 Section；
- 长 Section 按段落拆分；
- 同 Section 短尾块回并；
- 跨 Section 回并 bad case；
- 回并后超过上限 bad case；
- 无内容丢失和顺序错乱；
- 相同输入结果稳定。

### P1：第一版生产切块必须有

- token 上限；
- 不跨 Section 合并；
- code/table/list 结构保护；
- parent-child 引用一致；
- offset/line range 可回溯；
- Golden File 回归；
- 20～50 条真实检索 eval case；
- Recall@K、上下文 token 和失败 case 报告。

### P2：规模增长后补充

- 属性测试和随机畸形文档；
- PDF 版面、OCR、表格专项测试；
- 多文档类型策略矩阵；
- 增量索引与稳定 ID 测试；
- 大文档性能、内存和并发压测；
- 不同 embedding、chunk size、overlap 的自动实验平台。

## 14. Java 到 Python 的正确迁移顺序

不建议逐行翻译 Java 循环。建议分四步：

### 阶段一：固定 Java baseline

先为当前行为补测试和固定输入输出，明确哪些是预期行为，哪些只是已知缺陷。

### 阶段二：Python 行为对齐

Python 版本先跑相同 fixtures，确保文档解析、标题路径、内容顺序和 metadata 没有无意变化。

### 阶段三：替换生产策略

逐项替换：

```text
手写 Markdown 行解析 -> Markdown AST parser
字符阈值 -> 目标模型 token 阈值
全局向前回并 -> 同 Section、结构兼容、预算约束合并
单层 chunk -> parent-child
无位置 -> offset/line range
index+content ID -> 稳定文档/章节/版本 identity
```

每替换一项都运行结构测试、Golden File diff 和检索 eval，避免同时修改多个变量后无法定位回归原因。

### 阶段四：按数据调参

依据真实失败 case 调整，而不是为了让平均 chunk 长度更“漂亮”。如果一个改动提升总体 Recall@K，却让代码和表格问题明显退化，应按 `docType/contentType` 拆分策略，而不是继续寻找全局唯一参数。

## 15. 设计评审检查表

设计或评审一个切块模块时，应能回答：

- 输入支持哪些文档类型？每种类型使用什么 parser？
- 文档清洗发生在切块前还是切块后？删除内容是否可审计？
- 语义边界和长度边界的优先级是什么？
- 使用字符数还是实际 tokenizer？
- 哪些结构绝不能从中间切开？
- 短块可以与谁合并？是否重新检查 token 上限？
- 是否采用 parent-child 或邻块扩展？
- overlap 的目的是什么？重复内容如何去重？
- chunk 是否能准确定位回原文？
- ID 在文档局部变化后是否尽量稳定？
- 权限信息在 chunk 上如何继承和过滤？
- chunker 配置和版本是否写入索引？
- 如何比较两种策略？有哪些真实 eval case？
- 发布新策略时如何灰度、重建、回滚和对比旧索引？

## 16. 面试表达

可以这样概括当前实现：

> DAY1 的 Java 原型采用两阶段切块：先按 Markdown 标题建立 Section 和 sectionPath，保留作者定义的语义边界；章节过长时再按段落拆分，单段仍过长才按字符 fallback；小于 120 字符的 part 会尝试回并。这个实现透明、便于学习，但我通过代码分析发现它会跨 Section 回并、回并后可能突破最大长度、代码块和表格可能被硬切，而且字符数不等于模型 token，因此它只适合作为 baseline。

可以这样概括生产设计：

> 生产版我会使用结构感知、token-aware 的 parent-child 切块。先用文档 parser 识别标题、段落、代码、表格和列表，构造不可破坏的原子块；再生成较小 child 用于精准检索，命中后按 parent 或相邻 child 扩展回答上下文。每个 chunk 保存稳定文档身份、标题路径、父子关系、offset、tokenCount、hash 和 chunkerVersion。策略质量不靠经验参数判断，而是通过结构不变量测试、Golden File、属性测试和真实问题集上的 Recall@K、引用正确性、上下文噪声与 token 成本共同验证。

## 17. 最终结论

当前 `MarkdownChunker` 的核心思路没有错：

```text
先尊重标题结构
再处理长度上限
最后减少过短碎片
```

它的问题在于规则过于粗糙：

```text
结构识别不完整
使用字符而不是 token
回并不限制 Section
回并后不重新校验大小
不保护代码、表格和列表
没有 parent-child、位置与版本
没有自动化测试和检索效果对比
```

本项目生产版最合适的演进方向是：

```text
Markdown AST / 文档结构解析
  + token-aware 递归切分
  + 原子结构保护
  + parent-child / neighbor expansion
  + 稳定 ID、offset、版本和权限 metadata
  + 单元测试、属性测试、Golden File 和 RAG eval
```

切块的工程目标不是“把文档切成若干段”，而是生成**可检索、可组合、可引用、可回溯、可评估、可安全更新**的知识单元。
