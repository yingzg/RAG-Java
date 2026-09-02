package com.example.rag.retrieval;

public record SearchQuery(String text, int topK) {
    public SearchQuery {
        if (topK <= 0) {
            topK = 5;
        }
    }
}
