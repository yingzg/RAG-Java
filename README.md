# RAG-Java

RAG-Java is now organized as an independent **RAG Knowledge Service** project, not as logic embedded inside a Java business service.

The architecture decision is:

```text
prototype-cli       # Java CLI prototype for learning the RAG mechanics
rag-service-python  # formal independent RAG service, Python/FastAPI first
rag-mcp-server      # TypeScript MCP adapter, calls rag-service-python over HTTP
docs                # architecture, API, MCP, security, language decisions
eval                # shared eval cases and reports, promoted from prototype later
```

## Why This Shape

RAG is a cross-cutting knowledge/context capability. It should own document ingestion, chunking, indexing, retrieval, generation, citation, refusal, eval, and trace. Java business services, MCP servers, agents, and frontends should call it through APIs instead of embedding the RAG pipeline inside business code.

## Language Decision

Formal RAG service: **Python FastAPI**.

Reasons:

- RAG frameworks, embedding/rerank integrations, eval tooling, and experimentation velocity are strongest in Python.
- The RAG service is independent, so Java business systems can still integrate through HTTP.
- MCP/Agent adapter will be TypeScript, matching the strongest MCP ecosystem path.
- The Java CLI prototype remains valuable as a transparent learning and diagnostic tool, not the production service.

See [language-decision.md](docs/language-decision.md).

## Design Documentation

- [RAG chunking design](docs/chunking-design.md): explains the current `MarkdownChunker`, short-block merge behavior, production chunking strategies, and the automated test/eval plan.

## Subprojects

### `prototype-cli`

The completed Day1 Java CLI prototype:

```bash
cd prototype-cli
mvn package
java -jar target/rag-java-0.1.0.jar index
java -jar target/rag-java-0.1.0.jar search "Dubbo 服务异常应该如何封装？"
java -jar target/rag-java-0.1.0.jar answer "生产数据库密码是什么？"
java -jar target/rag-java-0.1.0.jar eval
```

Purpose:

- Learn and inspect RAG mechanics.
- Validate source documents, chunking, metadata, citation, refusal, trace, and eval.
- Provide a reference implementation for the formal service.

### `rag-service-python`

Formal RAG Knowledge Service skeleton:

```text
POST /api/v1/index/rebuild
POST /api/v1/search
POST /api/v1/answer
GET  /api/v1/traces/{trace_id}
POST /api/v1/eval/run
```

Day1.5 skeleton intentionally starts with a local JSONL store and keyword retriever compatible with the prototype output. Day2 will add embedding and vector store support.

### `rag-mcp-server`

TypeScript MCP adapter skeleton. It exposes:

```text
doc.search
rag.answer
rag.eval.run
```

The MCP server calls `rag-service-python` over HTTP. It does not own indexing or vector storage.
