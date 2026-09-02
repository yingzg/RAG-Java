package com.example.rag.retrieval;

import com.example.rag.document.DocumentChunk;
import com.example.rag.util.JsonUtil;

import java.util.List;

public record SearchResult(
        DocumentChunk chunk,
        double score,
        List<String> matchedTerms,
        List<String> matchReasons
) {
    public String toTraceJson() {
        return "{"
                + "\"chunk_id\":" + JsonUtil.quote(chunk.chunkId())
                + ",\"score\":" + String.format(java.util.Locale.ROOT, "%.2f", score)
                + ",\"source_name\":" + JsonUtil.quote(chunk.sourceName())
                + ",\"source_path\":" + JsonUtil.quote(chunk.sourcePath())
                + ",\"section_path\":" + JsonUtil.quote(chunk.sectionPath())
                + ",\"matched_terms\":" + JsonUtil.array(matchedTerms)
                + ",\"match_reasons\":" + JsonUtil.array(matchReasons)
                + "}";
    }
}
