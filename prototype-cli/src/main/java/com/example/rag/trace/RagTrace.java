package com.example.rag.trace;

import com.example.rag.retrieval.SearchResult;
import com.example.rag.util.JsonUtil;

import java.time.Instant;
import java.util.List;

public record RagTrace(
        String traceId,
        String type,
        String question,
        int topK,
        List<SearchResult> retrievedChunks,
        boolean refused,
        long latencyMs,
        Instant createdAt
) {
    public String toJson() {
        StringBuilder chunks = new StringBuilder("[");
        for (int i = 0; i < retrievedChunks.size(); i++) {
            if (i > 0) {
                chunks.append(',');
            }
            chunks.append(retrievedChunks.get(i).toTraceJson());
        }
        chunks.append(']');
        return "{"
                + "\"trace_id\":" + JsonUtil.quote(traceId)
                + ",\"type\":" + JsonUtil.quote(type)
                + ",\"question\":" + JsonUtil.quote(question)
                + ",\"top_k\":" + topK
                + ",\"retrieved_chunks\":" + chunks
                + ",\"refused\":" + refused
                + ",\"latency_ms\":" + latencyMs
                + ",\"created_at\":" + JsonUtil.quote(createdAt.toString())
                + "}";
    }
}
