package com.example.rag.index;

import com.example.rag.document.DocumentChunk;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class JsonlChunkStore {
    private final Path path;

    public JsonlChunkStore(Path path) {
        this.path = path;
    }

    public void save(List<DocumentChunk> chunks) throws IOException {
        Files.createDirectories(path.getParent());
        try (BufferedWriter writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
            for (DocumentChunk chunk : chunks) {
                writer.write(chunk.toJson());
                writer.newLine();
            }
        }
    }

    public ChunkIndex load() throws IOException {
        if (!Files.exists(path)) {
            return new ChunkIndex(List.of());
        }
        List<DocumentChunk> chunks = new ArrayList<>();
        for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
            if (!line.isBlank()) {
                chunks.add(DocumentChunk.fromJson(line));
            }
        }
        return new ChunkIndex(chunks);
    }

    public Path path() {
        return path;
    }
}
