package com.example.rag.retrieval;

import com.example.rag.index.ChunkIndex;

import java.util.List;

public interface Retriever {
    List<SearchResult> search(SearchQuery query, ChunkIndex index);
}
