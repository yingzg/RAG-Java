# rag-mcp-server

TypeScript MCP adapter for the independent RAG Knowledge Service.

It is intentionally thin:

```text
MCP client / Agent / IDE
  -> rag-mcp-server
  -> rag-service-python HTTP API
```

The MCP server should not parse documents, build embeddings, or query vector stores directly.

## Tools

- `doc.search`: calls `POST /api/v1/search`
- `rag.answer`: calls `POST /api/v1/answer`
- `rag.eval.run`: calls `POST /api/v1/eval/run`

## Planned Run

```bash
cd rag-mcp-server
npm install
npm run build
RAG_SERVICE_BASE_URL=http://localhost:8000 node dist/index.js
```

Day1.5 provides the project skeleton and schemas. Full MCP runtime verification comes after dependencies are installed.
