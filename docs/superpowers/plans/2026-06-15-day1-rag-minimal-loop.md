# Day1 RAG Minimal Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Java CLI RAG Day1 minimal production-shaped loop for Markdown knowledge bases.

**Architecture:** A no-dependency Java 17 Maven project with a focused core: load Markdown files, split them into metadata-rich chunks, persist chunks as JSONL, retrieve by keyword scoring, build citation-backed template answers, record traces, and run a small eval suite. The code keeps retriever/store interfaces stable so Day2 can add embeddings and vector search without rewriting the pipeline.

**Tech Stack:** Java 17, Maven, JDK standard library only, JSONL files for Day1 persistence.

---

### Task 1: Project Skeleton

**Files:**
- Create: `pom.xml`
- Create: `README.md`
- Create: `config/sources.json`
- Create: `docs/day1-design.md`

- [x] Create Maven structure and CLI entrypoint package.
- [x] Configure Java 17 compilation and executable jar manifest.
- [x] Document Day1 commands and scope.

### Task 2: Document Ingestion And Chunking

**Files:**
- Create: `src/main/java/com/example/rag/config/DocumentSource.java`
- Create: `src/main/java/com/example/rag/config/SourceConfigLoader.java`
- Create: `src/main/java/com/example/rag/document/RawDocument.java`
- Create: `src/main/java/com/example/rag/document/DocumentChunk.java`
- Create: `src/main/java/com/example/rag/document/MarkdownLoader.java`
- Create: `src/main/java/com/example/rag/document/MarkdownChunker.java`
- Create: `src/main/java/com/example/rag/document/MetadataExtractor.java`

- [x] Load the four configured Markdown source roots.
- [x] Exclude `.git`, `.vibe`, `.vkf`, build directories, scripts, and non-Markdown files.
- [x] Chunk by Markdown headings and split oversized chunks by paragraph.
- [x] Preserve source name, source path, file name, section path, doc type, chunk index, and content length.

### Task 3: Index Persistence

**Files:**
- Create: `src/main/java/com/example/rag/index/ChunkIndex.java`
- Create: `src/main/java/com/example/rag/index/JsonlChunkStore.java`
- Create: `src/main/java/com/example/rag/index/IndexService.java`
- Create: `src/main/java/com/example/rag/util/JsonUtil.java`
- Create: `src/main/java/com/example/rag/util/TextUtil.java`

- [x] Write chunks to `data/index/chunks.jsonl`.
- [x] Read chunks from the JSONL store for search, answer, and eval.
- [x] Print document and chunk counts after indexing.

### Task 4: Retrieval, Answer, Trace, Eval

**Files:**
- Create: `src/main/java/com/example/rag/retrieval/SearchQuery.java`
- Create: `src/main/java/com/example/rag/retrieval/SearchResult.java`
- Create: `src/main/java/com/example/rag/retrieval/Retriever.java`
- Create: `src/main/java/com/example/rag/retrieval/QueryTokenizer.java`
- Create: `src/main/java/com/example/rag/retrieval/KeywordRetriever.java`
- Create: `src/main/java/com/example/rag/answer/RagAnswer.java`
- Create: `src/main/java/com/example/rag/answer/RefusalPolicy.java`
- Create: `src/main/java/com/example/rag/answer/AnswerBuilder.java`
- Create: `src/main/java/com/example/rag/trace/RagTrace.java`
- Create: `src/main/java/com/example/rag/trace/TraceRecorder.java`
- Create: `src/main/java/com/example/rag/eval/EvalCase.java`
- Create: `src/main/java/com/example/rag/eval/EvalResult.java`
- Create: `src/main/java/com/example/rag/eval/EvalRunner.java`
- Create: `src/main/java/com/example/rag/RagCliApplication.java`

- [x] Implement `index`, `search`, `answer`, and `eval` commands.
- [x] Score phrase, title, filename, source, doc type, and content matches.
- [x] Output citations, matched terms, scores, and trace ids.
- [x] Refuse low-evidence and sensitive questions.
- [x] Write traces to `data/traces`.
- [x] Seed Day1 eval cases in `data/eval/rag_cases.jsonl` when missing.

### Task 5: Verification

- [x] Run `mvn package`.
- [x] Run `java -jar target/rag-java-0.1.0.jar index`.
- [x] Run representative `search` and `answer` commands.
- [x] Run `java -jar target/rag-java-0.1.0.jar eval`.
