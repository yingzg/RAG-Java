# RAG DAY1 Code Learning Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete DAY1 learning-note set that explains the Java RAG prototype at the correct depth and maps its language-independent design to the Python service.

**Architecture:** Keep Java source files unchanged and create focused Markdown notes under `docs/learning/day1/`. Follow the actual RAG data flow: entrypoint, chunk schema, chunking, retrieval, offline indexing, answer/refusal/trace, evaluation, then Java-to-Python mapping. Validate every note against current source line numbers and explicitly distinguish the DAY1 heuristic prototype from production RAG.

**Tech Stack:** Markdown, Java 17 source, Python 3/FastAPI source, Maven verification, `rg`/`sed`/`wc` for documentation checks.

---

## File map

| Output file | Single responsibility |
|---|---|
| `docs/learning/day1/01-rag-cli-application.md` | Explain the four CLI use cases and provide the complete project execution map. |
| `docs/learning/day1/02-document-chunk.md` | Explain the chunk data contract and why each metadata field exists. |
| `docs/learning/day1/03-markdown-chunker.md` | Explain heading-aware chunking, oversized splitting, short-block merging, IDs, and edge cases. |
| `docs/learning/day1/04-keyword-retriever.md` | Explain tokenization, weighted keyword scoring, sorting, top-k, and heuristic limitations. |
| `docs/learning/day1/05-offline-index-pipeline.md` | Explain source configuration, loading, metadata, rebuilding, and JSONL persistence. |
| `docs/learning/day1/06-answer-refusal-trace.md` | Explain evidence formatting, refusal gates, citations, and trace recording. |
| `docs/learning/day1/07-eval-runner.md` | Explain seeded eval cases, execution, pass criteria, reporting, and metric gaps. |
| `docs/learning/day1/08-java-to-python-mapping.md` | Map RAG capabilities and design decisions from the Java prototype to the Python service. |

Java source files are read-only inputs. No task modifies files under `prototype-cli/src` or `rag-service-python/app`.

Every output lesson `01` through `08` must retain the design contract, adapted to its topic: learning goals; RAG-chain position; responsibility; upstream/downstream dependencies; input/process/output; pseudocode before source details; core code explanation; skippable engineering code; worked example; current limitations; production evolution; Java-to-Python mapping; interview explanation; and self-test questions with answers. A focused lesson may combine adjacent items under one heading, but none may be omitted.

The current project directory is not a Git repository and has no worktree support. Execute this documentation plan in place, do not modify source files, and do not fabricate the commit steps that would normally accompany an implementation plan.

### Task 1: Explain the CLI entrypoint and four RAG use cases

**Files:**
- Create: `docs/learning/day1/01-rag-cli-application.md`
- Read: `prototype-cli/src/main/java/com/example/rag/RagCliApplication.java:24`
- Reference: `docs/project-learning-guide.md:117`

- [ ] **Step 1: Capture the source structure**

Run:

```bash
rg -n '^\s*(public|private).*[({]|^\s*private record' prototype-cli/src/main/java/com/example/rag/RagCliApplication.java
```

Expected: entries for `main`, `run`, `index`, `search`, `answer`, `eval`, `loadRequiredIndex`, `printResults`, `parseQueryArgs`, `elapsedMillis`, `printHelp`, and `QueryArgs`.

- [ ] **Step 2: Write the fixed teaching sections**

Create the note with these exact top-level sections:

```markdown
# 01. RagCliApplication：先看懂整个 RAG 最小闭环
## 1. 本节学习目标
## 2. 它在 RAG 链路中的位置
## 3. 类级结构与依赖
## 4. main 和 run：命令如何分发
## 5. index：离线索引链路
## 6. search：在线检索链路
## 7. answer：检索、拒答、引用与 trace
## 8. eval：固定问题如何评估
## 9. 辅助方法与可以略读的代码
## 10. 一次完整执行推演
## 11. 当前实现的边界和问题
## 12. Java 到 Python 的映射
## 13. 面试表达
## 14. 自测题与参考答案
```

- [ ] **Step 3: Add line-by-line explanations for the orchestration paths**

Cover these exact ranges and decisions:

- Lines 25-35: paths and long-lived collaborators.
- Lines 37-57: process entry and command dispatch.
- Lines 60-73: source loading and index rebuilding.
- Lines 76-90: index loading, retrieval, timing, trace, output.
- Lines 93-118: retrieval before answer building, refusal state, citations.
- Lines 121-139: eval runner and output fields.
- Lines 142-183: empty-index gate and CLI argument parsing.

For each range, include the original code block, a numbered explanation, the RAG concept it represents, and whether it is core RAG or CLI engineering.

- [ ] **Step 4: Add a concrete execution trace**

Use `answer "聚合根为什么要保证一致性边界？" --topK 3` and trace the exact objects:

```text
String[] args
  -> QueryArgs(question, 3)
  -> ChunkIndex
  -> SearchQuery
  -> List<SearchResult>
  -> RagAnswer
  -> RagTrace
  -> console answer + citations
```

State explicitly that `AnswerBuilder` produces a template, not an LLM-generated answer.

- [ ] **Step 5: Verify note coverage**

Run:

```bash
rg -n '^## ' docs/learning/day1/01-rag-cli-application.md
rg -n 'index|search|answer|eval|模板|Python|自测题' docs/learning/day1/01-rag-cli-application.md
```

Expected: all 14 headings and all four commands appear; “模板” identifies the current answer implementation.

### Task 2: Explain the chunk data contract

**Files:**
- Create: `docs/learning/day1/02-document-chunk.md`
- Read: `prototype-cli/src/main/java/com/example/rag/document/DocumentChunk.java:5`
- Read: `prototype-cli/src/main/java/com/example/rag/document/RawDocument.java:5`

- [ ] **Step 1: Document the raw-to-chunk boundary**

Use this model transition:

```text
RawDocument
  source + absolutePath + relativePath + full content
          |
          v MarkdownChunker
DocumentChunk
  identity + source metadata + section metadata + partial content
```

- [ ] **Step 2: Explain every `DocumentChunk` field**

For `chunkId`, `sourceName`, `sourceRoot`, `sourcePath`, `fileName`, `sectionPath`, `chunkIndex`, `docType`, `content`, and `contentLength`, include:

- where the value comes from;
- what downstream feature consumes it;
- whether it should be searchable, filterable, returned as a citation, or internal only;
- what production concern it supports: idempotency, tenant isolation, permission, versioning, debugging, or display.

- [ ] **Step 3: Explain serialization without teaching custom JSON internals**

Explain `toJson` and `fromJson` as persistence boundaries. State why `JsonUtil` is an implementation detail and why Python will use Pydantic/standard JSON handling instead of porting it.

- [ ] **Step 4: Verify field completeness**

Run:

```bash
for field in chunkId sourceName sourceRoot sourcePath fileName sectionPath chunkIndex docType content contentLength; do rg -q "$field" docs/learning/day1/02-document-chunk.md || exit 1; done
```

Expected: exit code `0`.

### Task 3: Explain Markdown chunking in depth

**Files:**
- Create: `docs/learning/day1/03-markdown-chunker.md`
- Read: `prototype-cli/src/main/java/com/example/rag/document/MarkdownChunker.java:8`
- Read: `prototype-cli/src/main/java/com/example/rag/util/TextUtil.java:1`

- [ ] **Step 1: Present the algorithm before the Java implementation**

Include this flow:

```text
RawDocument
  -> normalize source metadata
  -> split Markdown into heading sections
  -> split sections longer than 1200 characters
  -> merge a block shorter than 120 characters into the previous chunk
  -> generate deterministic chunkId
  -> create DocumentChunk list
```

- [ ] **Step 2: Explain `chunk` line by line**

Cover lines 14-47, including the mutation of `chunkIndex` when a short part replaces the previous chunk. Use an explicit two-part example to show why the previous chunk is removed and re-created.

- [ ] **Step 3: Explain heading state management**

Cover lines 49-80 and 111-135. Demonstrate heading state with:

```markdown
# Dubbo
## Timeout
### Retry
## Exception
```

Expected paths:

```text
Dubbo
Dubbo > Timeout
Dubbo > Timeout > Retry
Dubbo > Exception
```

- [ ] **Step 4: Explain oversized splitting and enumerate edge cases**

Cover lines 82-109. Include these cases:

- a section under 1200 characters;
- multiple paragraphs that cross 1200 characters;
- one paragraph longer than 1200 characters;
- a final short block;
- an initial short block with no previous chunk;
- a small section merged across a heading boundary;
- a long code block split by raw character count.

Call out the last two as quality risks in the current implementation.

- [ ] **Step 5: Compare character length with token-aware and structure-aware production chunking**

Explain why Python should preserve the behavior as a baseline test, then evolve toward token budgets, Markdown AST parsing, code-block preservation, overlap or parent-child chunks based on eval results.

- [ ] **Step 6: Verify critical terms**

Run:

```bash
rg -n '1200|120|sectionPath|chunkId|标题|代码块|token|parent-child' docs/learning/day1/03-markdown-chunker.md
```

Expected: each term is discussed in algorithm or production-analysis sections.

### Task 4: Explain keyword retrieval and scoring

**Files:**
- Create: `docs/learning/day1/04-keyword-retriever.md`
- Read: `prototype-cli/src/main/java/com/example/rag/retrieval/QueryTokenizer.java:12`
- Read: `prototype-cli/src/main/java/com/example/rag/retrieval/KeywordRetriever.java:14`
- Read: `prototype-cli/src/main/java/com/example/rag/retrieval/SearchResult.java:1`

- [ ] **Step 1: Explain tokenization with one Chinese/English query**

Use `Dubbo 服务异常应该如何封装？` and show:

- ASCII tokens such as `Dubbo` and lowercase `dubbo`;
- removal of ASCII text before Chinese n-grams;
- Chinese 2-grams and 3-grams;
- stop-word removal;
- insertion-order de-duplication through `LinkedHashSet`.

- [ ] **Step 2: Explain search orchestration lines 18-32**

Show normalization, query tokenization, full index scan, filtering scores above zero, descending sort, and `topK` truncation. State time complexity as approximately `O(number_of_chunks × tokens × text_scan)` for this implementation.

- [ ] **Step 3: Explain every scoring rule lines 35-86**

Document the exact weights:

| Match | Score |
|---|---:|
| Full query phrase in content | +20 |
| Token in section path | +8 |
| Token in file name | +6 |
| Token in source name | +5 |
| Token in content | +2 per hit, capped at +12 per token |
| `deep_dive` / `rebuild_guide` prior | +2 when already matched |
| `index` prior | +1 when already matched |

- [ ] **Step 4: Manually score one synthetic chunk**

Show the arithmetic and the resulting `matchedTerms` and `reasons`. Explain that the scores are heuristic relevance values, not calibrated probabilities and not cosine similarity.

- [ ] **Step 5: Explain limitations and migration**

Cover full index scans, substring false positives, overlapping n-gram double counting, document-length bias, no IDF, no metadata filters, no tie-break rule, and no score normalization. Map the future design to BM25 + vector retrieval + fusion + rerank.

- [ ] **Step 6: Verify scoring completeness**

Run:

```bash
rg -n '\+20|\+8|\+6|\+5|\+2|12|topK|O\(' docs/learning/day1/04-keyword-retriever.md
```

Expected: all weights, the cap, top-k, and complexity appear.

### Task 5: Explain the offline indexing pipeline

**Files:**
- Create: `docs/learning/day1/05-offline-index-pipeline.md`
- Read: `prototype-cli/src/main/java/com/example/rag/config/DocumentSource.java:5`
- Read: `prototype-cli/src/main/java/com/example/rag/config/SourceConfigLoader.java:15`
- Read: `prototype-cli/src/main/java/com/example/rag/document/MarkdownLoader.java:16`
- Read: `prototype-cli/src/main/java/com/example/rag/document/MetadataExtractor.java:3`
- Read: `prototype-cli/src/main/java/com/example/rag/index/IndexService.java:15`
- Read: `prototype-cli/src/main/java/com/example/rag/index/JsonlChunkStore.java:13`
- Read: `prototype-cli/config/sources.json:1`

- [ ] **Step 1: Trace configuration to persisted chunks**

Use this exact pipeline:

```text
sources.json
  -> SourceConfigLoader
  -> List<DocumentSource>
  -> MarkdownLoader
  -> List<RawDocument>
  -> MarkdownChunker + MetadataExtractor
  -> List<DocumentChunk>
  -> JsonlChunkStore
  -> data/index/chunks.jsonl
```

- [ ] **Step 2: Explain portable path resolution and loading rules**

Cover Windows/WSL path conversion, nonexistent-directory behavior, UTF-8 reads, `.md` filtering, excluded directories, stable sorting, and blank-document filtering.

- [ ] **Step 3: Explain full rebuild semantics**

Cover `IndexService.rebuild`, source/document/chunk counts, deterministic ordering, whole-index replacement, and what is missing for incremental indexing: content hash comparison, deletion detection, version fields, atomic swap, and failed-document isolation.

- [ ] **Step 4: Explain JSONL as an educational store**

State its advantages for inspection and portability, then its production limits: full-file load, no vector index, no transactional update, no concurrent writer coordination, no metadata query index, and no permission enforcement.

- [ ] **Step 5: Verify all pipeline components appear**

Run:

```bash
rg -n 'SourceConfigLoader|DocumentSource|MarkdownLoader|RawDocument|MarkdownChunker|MetadataExtractor|JsonlChunkStore|chunks.jsonl' docs/learning/day1/05-offline-index-pipeline.md
```

Expected: all eight pipeline components appear in the note.

### Task 6: Explain answer building, refusal, citations, and trace

**Files:**
- Create: `docs/learning/day1/06-answer-refusal-trace.md`
- Read: `prototype-cli/src/main/java/com/example/rag/answer/AnswerBuilder.java:8`
- Read: `prototype-cli/src/main/java/com/example/rag/answer/RefusalPolicy.java:8`
- Read: `prototype-cli/src/main/java/com/example/rag/answer/RagAnswer.java:1`
- Read: `prototype-cli/src/main/java/com/example/rag/trace/RagTrace.java:1`
- Read: `prototype-cli/src/main/java/com/example/rag/trace/TraceRecorder.java:11`

- [ ] **Step 1: Separate four concerns**

Define them independently:

```text
answer formatting  = turn retrieved evidence into readable output
refusal            = decide whether answering is allowed/supported
citation           = identify the source chunks used as evidence
trace              = persist what happened during one request
```

- [ ] **Step 2: Explain `AnswerBuilder` lines 11-49**

Show the branch between `answerText` and `refusalText`. Explain why returning previews of top-k chunks is evidence presentation, not semantic summarization by an LLM.

- [ ] **Step 3: Explain refusal policy lines 14-36 and identify the policy bug**

Cover the sensitive-term check and the score threshold `8.0`. Explicitly identify that substring matching `ak` and `sk` can create false positives inside unrelated text, and that security refusal and lack-of-evidence refusal should produce distinct policy codes in production.

- [ ] **Step 4: Explain citation provenance**

Trace `SearchResult.chunk()` fields into the printed citation. Distinguish “citation exists” from “citation correctly supports the generated claim”; the DAY1 implementation only guarantees the former.

- [ ] **Step 5: Explain trace identity and contents**

Cover trace ID generation, JSON persistence, request type, question, top-k, retrieved results, refusal state, latency, and creation time. List missing production fields: model/provider, prompt version, token counts, filter/rerank stages, errors, tenant/user, index version, and correlation ID.

- [ ] **Step 6: Verify the conceptual separation**

Run:

```bash
rg -n '模板|LLM|拒答|8\.0|ak|sk|引用|citation|trace|token|index version' docs/learning/day1/06-answer-refusal-trace.md
```

Expected: implementation truth, threshold, false-positive risk, provenance, and production trace gaps appear.

### Task 7: Explain evaluation and bad-case diagnosis

**Files:**
- Create: `docs/learning/day1/07-eval-runner.md`
- Read: `prototype-cli/src/main/java/com/example/rag/eval/EvalRunner.java:17`
- Read: `prototype-cli/src/main/java/com/example/rag/eval/EvalCase.java:1`
- Read: `prototype-cli/src/main/java/com/example/rag/eval/EvalResult.java:1`
- Read: `prototype-cli/data/eval/rag_cases.jsonl:1`

- [ ] **Step 1: Explain the eval data contract**

Cover case ID, question, expected source, refusal expectation, notes, actual top source, top score, refusal result, pass/fail, and reason.

- [ ] **Step 2: Explain the run loop lines 29-51**

Show how each case creates a `SearchQuery`, runs retrieval, evaluates refusal, inspects the top source, and calculates pass/fail. Explain why the current non-refusal criterion is effectively top-1 source accuracy rather than recall@k.

- [ ] **Step 3: Explain seed cases and report generation**

Cover auto-creation behavior, JSONL loading, Markdown report totals, pass rate, refusal correctness, and per-case output.

- [ ] **Step 4: Build a failure taxonomy**

Use these categories:

```text
ingestion failure
chunking failure
retrieval failure
ranking failure
refusal-policy failure
generation failure (future Day3)
citation-grounding failure (future Day3)
```

For each category, state which trace/eval signal would reveal it.

- [ ] **Step 5: Define the production metric progression**

Explain recall@k, MRR/nDCG as optional ranking metrics, citation correctness, answer correctness, refusal precision/recall, hallucination/faithfulness, latency percentiles, token usage, and cost. Do not claim all metrics must be built on DAY1.

- [ ] **Step 6: Verify metric and failure coverage**

Run:

```bash
rg -n 'top-1|recall@k|MRR|citation|refusal|ingestion failure|chunking failure|retrieval failure|generation failure' docs/learning/day1/07-eval-runner.md
```

Expected: current metric semantics and the full bad-case taxonomy appear.

### Task 8: Map Java capabilities to the Python service

**Files:**
- Create: `docs/learning/day1/08-java-to-python-mapping.md`
- Read: `rag-service-python/app/main.py:1`
- Read: `rag-service-python/app/service.py:30`
- Read: `rag-service-python/app/retrieval.py:34`
- Read: `rag-service-python/app/store.py:9`
- Read: `rag-service-python/app/models.py:1`
- Read: `rag-service-python/app/settings.py:1`
- Reference: `docs/language-decision.md:1`

- [ ] **Step 1: Build the capability mapping table**

Include these rows:

| Capability | Java prototype | Python current/future |
|---|---|---|
| transport/orchestration | CLI methods | FastAPI endpoint + application service |
| chunk model | `DocumentChunk` | Pydantic/store `Chunk` model |
| local persistence | `JsonlChunkStore` | Python `JsonlChunkStore`, later vector/search store |
| keyword retrieval | `QueryTokenizer` + `KeywordRetriever` | Python equivalents, later BM25 branch |
| answer | `AnswerBuilder` template | prompt builder + LLM client + grounded response |
| refusal | score/sensitive substring rules | evidence gate + security policy |
| trace | JSON files | trace repository/observability backend |
| eval | `EvalRunner` | repeatable eval service/pipeline |

- [ ] **Step 2: Explain the FastAPI boundary**

Trace `/api/v1/search` and `/api/v1/answer` from request models through `RagApplicationService` to retriever/store and response models. Emphasize that HTTP service boundaries are architecture, not RAG algorithms.

- [ ] **Step 3: Separate preserve, replace, and add decisions**

Use these groups:

```text
Preserve:
  chunk schema intent, citation provenance, refusal concept, trace/eval discipline

Replace:
  CLI transport, custom JSON parser, raw full-scan persistence, Java-specific path handling

Add:
  embedding, vector store, hybrid fusion, rerank, LLM generation,
  citation validation, metadata filters, index versioning, production observability
```

- [ ] **Step 4: Provide a Python ownership-depth guide**

State which Python code must be explainable line by line (owned RAG policy and pipeline), which needs interface-level understanding (FastAPI/Pydantic/client libraries), and which should remain a black-box dependency with contract tests (model provider and vector database internals).

- [ ] **Step 5: Verify migration language**

Run:

```bash
rg -n 'Preserve|Replace|Add|embedding|vector|hybrid|rerank|LLM|citation|FastAPI|Pydantic' docs/learning/day1/08-java-to-python-mapping.md
```

Expected: capability preservation and all future RAG components appear without a line-by-line translation requirement.

### Task 9: Final consistency and non-regression verification

**Files:**
- Verify: `docs/learning/day1/00-learning-notes-design.md`
- Verify: `docs/learning/day1/01-rag-cli-application.md`
- Verify: `docs/learning/day1/02-document-chunk.md`
- Verify: `docs/learning/day1/03-markdown-chunker.md`
- Verify: `docs/learning/day1/04-keyword-retriever.md`
- Verify: `docs/learning/day1/05-offline-index-pipeline.md`
- Verify: `docs/learning/day1/06-answer-refusal-trace.md`
- Verify: `docs/learning/day1/07-eval-runner.md`
- Verify: `docs/learning/day1/08-java-to-python-mapping.md`

- [ ] **Step 1: Check that all files exist and are non-empty**

Run:

```bash
for n in 00-learning-notes-design 01-rag-cli-application 02-document-chunk 03-markdown-chunker 04-keyword-retriever 05-offline-index-pipeline 06-answer-refusal-trace 07-eval-runner 08-java-to-python-mapping; do test -s "docs/learning/day1/$n.md" || exit 1; done
```

Expected: exit code `0`.

- [ ] **Step 2: Scan for incomplete text and implementation misrepresentation**

Run:

```bash
rg -n 'T[B]D|T[O]DO|待[补]充|以后[再]写|已经实现向量检索|已经接入LLM' docs/learning/day1
```

Expected: no output. Legitimate discussion of future vector/LLM work must say it is not implemented yet.

- [ ] **Step 3: Check design coverage in every lesson**

Run:

```bash
for f in docs/learning/day1/0[1-8]-*.md; do rg -q 'Python' "$f" || exit 1; rg -q '面试' "$f" || exit 1; done
```

Expected: exit code `0`; every lesson includes Python or migration context and interview framing.

- [ ] **Step 4: Verify the Java project still builds**

Run:

```bash
mvn -f prototype-cli/pom.xml package
```

Expected: `BUILD SUCCESS`. The notes must not require or introduce Java source changes.

- [ ] **Step 5: Record version-control limitation**

Run:

```bash
git status --short
```

Expected in the current directory state: Git reports that `RAG-Java` is not a repository. Do not fabricate commits; if the project is initialized later, commit the documentation as focused units.
