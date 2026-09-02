package com.example.rag.document;

import com.example.rag.config.DocumentSource;

import java.nio.file.Path;

public record RawDocument(
        DocumentSource source,
        Path absolutePath,
        Path relativePath,
        String content
) {
}
