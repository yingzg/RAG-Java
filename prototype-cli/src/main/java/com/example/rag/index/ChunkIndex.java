package com.example.rag.index;

import com.example.rag.document.DocumentChunk;

import java.util.List;

public record ChunkIndex(List<DocumentChunk> chunks) {
    public int size() {
        return chunks.size();
    }
}
