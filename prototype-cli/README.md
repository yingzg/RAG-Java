# RAG-Java

Day1 production-shaped minimal RAG loop for Java backend knowledge documents.

## Scope

Day1 intentionally avoids embedding, vector databases, LLM APIs, Spring Boot, MCP, and UI. It builds the core pipeline that those later layers will reuse:

```text
Markdown sources -> chunks with metadata -> local JSONL index -> keyword retrieval
  -> citation-backed answer -> refusal -> trace -> eval
```

## Commands

```bash
mvn package

java -jar target/rag-java-0.1.0.jar index
java -jar target/rag-java-0.1.0.jar search "Dubbo 服务异常应该如何封装？"
java -jar target/rag-java-0.1.0.jar answer "聚合根为什么要保证一致性边界？"
java -jar target/rag-java-0.1.0.jar eval
```

Optional topK:

```bash
java -jar target/rag-java-0.1.0.jar search "状态机适合什么业务场景？" --topK 8
```

## Indexed Sources

Configured in `config/sources.json`:

- `bff`: `/mnt/d/我的文件/学习文档/知识库/bff`
- `dubbo`: `/mnt/d/我的文件/学习文档/知识库/dubbo`
- `ddd`: `/mnt/d/个人项目/dddGuide`
- `state-machine`: `/mnt/d/测试项目/my-knowledge-projec/tatemachine-knowledge`

Day1 indexes Markdown files only and excludes `.git`, `.vibe`, `.vkf`, build directories, scripts, and generated artifacts.

## Windows / WSL Path Compatibility

`config/sources.json` uses WSL-style paths such as `/mnt/d/...`.

When running this CLI from Windows PowerShell, the application automatically maps those paths to Windows drive paths such as `D:\...`. When running from WSL, it uses `/mnt/d/...` directly.

If `index` outputs `Total chunks: 0`, check:

- The configured knowledge directories still exist.
- You are using the latest rebuilt `target/rag-java-0.1.0.jar`.
- `SourceConfigLoader` contains the portable path resolver.

Expected current index result:

```text
Total chunks: 1179
Documents by source:
  - bff: 25
  - dubbo: 47
  - ddd: 3
  - state-machine: 37
```

## Outputs

- Chunk index: `data/index/chunks.jsonl`
- Traces: `data/traces/*.json`
- Eval cases: `data/eval/rag_cases.jsonl`
- Eval report: `data/eval/rag_eval_report.md`
