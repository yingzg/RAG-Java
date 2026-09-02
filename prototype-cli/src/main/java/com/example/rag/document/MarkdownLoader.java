package com.example.rag.document;

import com.example.rag.config.DocumentSource;
import com.example.rag.util.TextUtil;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class MarkdownLoader {
    private static final Set<String> EXCLUDED_DIRS = Set.of(
            ".git", ".vibe", ".vkf", "target", "node_modules", ".idea", ".gradle", "build", "__pycache__"
    );

    public List<RawDocument> load(DocumentSource source) throws IOException {
        if (!Files.isDirectory(source.root())) {
            return List.of();
        }
        List<RawDocument> documents = new ArrayList<>();
        try (Stream<Path> paths = Files.walk(source.root())) {
            List<Path> markdownFiles = paths
                    .filter(Files::isRegularFile)
                    .filter(this::isMarkdown)
                    .filter(path -> !hasExcludedDirectory(source.root().relativize(path)))
                    .sorted(Comparator.comparing(Path::toString))
                    .toList();
            for (Path file : markdownFiles) {
                String content = TextUtil.normalize(Files.readString(file, StandardCharsets.UTF_8));
                if (!content.isBlank()) {
                    documents.add(new RawDocument(source, file, source.root().relativize(file), content));
                }
            }
        }
        return documents;
    }

    private boolean isMarkdown(Path path) {
        String name = path.getFileName().toString().toLowerCase();
        return name.endsWith(".md");
    }

    private boolean hasExcludedDirectory(Path relativePath) {
        for (Path part : relativePath) {
            if (EXCLUDED_DIRS.contains(part.toString())) {
                return true;
            }
        }
        return false;
    }
}
