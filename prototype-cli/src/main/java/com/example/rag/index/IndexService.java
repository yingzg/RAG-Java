package com.example.rag.index;

import com.example.rag.config.DocumentSource;
import com.example.rag.document.DocumentChunk;
import com.example.rag.document.MarkdownChunker;
import com.example.rag.document.MarkdownLoader;
import com.example.rag.document.RawDocument;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class IndexService {
    private final MarkdownLoader loader = new MarkdownLoader();
    private final MarkdownChunker chunker = new MarkdownChunker();
    private final JsonlChunkStore store;

    public IndexService(JsonlChunkStore store) {
        this.store = store;
    }

    public IndexSummary rebuild(List<DocumentSource> sources) throws IOException {
        List<DocumentChunk> allChunks = new ArrayList<>();
        Map<String, Integer> documentCounts = new LinkedHashMap<>();
        Map<String, Integer> chunkCounts = new LinkedHashMap<>();
        for (DocumentSource source : sources) {
            List<RawDocument> documents = loader.load(source);
            documentCounts.put(source.name(), documents.size());
            int chunksForSource = 0;
            for (RawDocument document : documents) {
                List<DocumentChunk> chunks = chunker.chunk(document);
                allChunks.addAll(chunks);
                chunksForSource += chunks.size();
            }
            chunkCounts.put(source.name(), chunksForSource);
        }
        store.save(allChunks);
        return new IndexSummary(documentCounts, chunkCounts, allChunks.size(), store.path().toString());
    }

    public record IndexSummary(
            Map<String, Integer> documentCounts,
            Map<String, Integer> chunkCounts,
            int totalChunks,
            String indexPath
    ) {
    }
}
