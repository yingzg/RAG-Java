package com.example.rag.answer;

import com.example.rag.retrieval.SearchResult;

import java.util.List;

public record RagAnswer(
        String traceId,
        String question,
        boolean refused,
        String text,
        List<SearchResult> evidence
) {
}
