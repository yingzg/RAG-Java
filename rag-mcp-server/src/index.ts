import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { RagClient } from "./ragClient.js";

const ragClient = new RagClient();

const server = new McpServer({
  name: "rag-mcp-server",
  version: "0.2.0"
});

server.tool(
  "doc.search",
  {
    query: z.string().min(1),
    domain: z.enum(["dubbo", "ddd", "state-machine", "bff", "notes", "rag-knowledge"]).optional(),
    doc_type: z.string().optional(),
    project: z.string().optional(),
    version: z.string().optional(),
    top_k: z.number().int().positive().max(20).optional(),
    mode: z.enum(["keyword", "vector", "hybrid"]).optional(),
    rerank: z.boolean().optional()
  },
  async (input) => {
    const result = await ragClient.search(input);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }]
    };
  }
);

server.tool(
  "rag.answer",
  {
    question: z.string().min(1),
    domain: z.enum(["dubbo", "ddd", "state-machine", "bff", "notes", "rag-knowledge"]).optional(),
    top_k: z.number().int().positive().max(20).optional(),
    require_citation: z.boolean().optional(),
    allow_refusal: z.boolean().optional()
  },
  async (input) => {
    const result = await ragClient.answer(input);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }]
    };
  }
);

server.tool(
  "rag.eval.run",
  {
    case_set: z.string().optional(),
    top_k: z.number().int().positive().max(20).optional()
  },
  async (input) => {
    const result = await ragClient.runEval(input);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }]
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
