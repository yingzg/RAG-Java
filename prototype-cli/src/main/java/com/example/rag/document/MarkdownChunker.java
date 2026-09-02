package com.example.rag.document;

import com.example.rag.util.TextUtil;

import java.util.ArrayList;
import java.util.List;

public class MarkdownChunker {
    private static final int MAX_CHUNK_CHARS = 1200;
    private static final int MIN_CHUNK_CHARS = 120;

    private final MetadataExtractor metadataExtractor = new MetadataExtractor();

    public List<DocumentChunk> chunk(RawDocument document) {
        String sourcePath = document.relativePath().toString().replace('\\', '/');
        String fileName = document.relativePath().getFileName().toString();
        String docType = metadataExtractor.docType(sourcePath);
        List<Section> sections = splitSections(document.content(), fileName);
        List<DocumentChunk> chunks = new ArrayList<>();
        int chunkIndex = 0;
        for (Section section : sections) {
            for (String part : splitOversized(section.content())) {
                String content = TextUtil.normalize(part);
                if (content.length() < MIN_CHUNK_CHARS && !chunks.isEmpty()) {
                    DocumentChunk previous = chunks.remove(chunks.size() - 1);
                    content = previous.content() + "\n\n" + content;
                    chunkIndex = previous.chunkIndex();
                }
                String seed = document.source().name() + "|" + sourcePath + "|" + chunkIndex + "|" + content;
                String chunkId = document.source().name() + "_" + TextUtil.sha1Short(seed);
                chunks.add(new DocumentChunk(
                        chunkId,
                        document.source().name(),
                        document.source().root().toString(),
                        sourcePath,
                        fileName,
                        section.sectionPath(),
                        chunkIndex,
                        docType,
                        content,
                        content.length()
                ));
                chunkIndex++;
            }
        }
        return chunks;
    }

    private List<Section> splitSections(String markdown, String fileName) {
        List<Section> sections = new ArrayList<>();
        String[] lines = markdown.split("\n");
        String[] headings = new String[6];
        StringBuilder current = new StringBuilder();
        String currentPath = stripExtension(fileName);

        for (String line : lines) {
            Heading heading = parseHeading(line);
            if (heading != null) {
                flushSection(sections, currentPath, current);
                headings[heading.level() - 1] = heading.title();
                for (int i = heading.level(); i < headings.length; i++) {
                    headings[i] = null;
                }
                currentPath = buildPath(headings, stripExtension(fileName));
                current.append(line).append('\n');
            } else {
                current.append(line).append('\n');
            }
        }
        flushSection(sections, currentPath, current);
        return sections.isEmpty() ? List.of(new Section(stripExtension(fileName), markdown)) : sections;
    }

    private void flushSection(List<Section> sections, String sectionPath, StringBuilder current) {
        String content = TextUtil.normalize(current.toString());
        if (!content.isBlank()) {
            sections.add(new Section(sectionPath, content));
        }
        current.setLength(0);
    }

    private List<String> splitOversized(String content) {
        if (content.length() <= MAX_CHUNK_CHARS) {
            return List.of(content);
        }
        List<String> parts = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        for (String paragraph : content.split("\\n\\s*\\n")) {
            if (current.length() + paragraph.length() + 2 > MAX_CHUNK_CHARS && current.length() > 0) {
                parts.add(current.toString());
                current.setLength(0);
            }
            if (paragraph.length() > MAX_CHUNK_CHARS) {
                for (int start = 0; start < paragraph.length(); start += MAX_CHUNK_CHARS) {
                    int end = Math.min(paragraph.length(), start + MAX_CHUNK_CHARS);
                    parts.add(paragraph.substring(start, end));
                }
            } else {
                if (current.length() > 0) {
                    current.append("\n\n");
                }
                current.append(paragraph);
            }
        }
        if (current.length() > 0) {
            parts.add(current.toString());
        }
        return parts;
    }

    private Heading parseHeading(String line) {
        String trimmed = line.trim();
        if (!trimmed.startsWith("#")) {
            return null;
        }
        int level = 0;
        while (level < trimmed.length() && trimmed.charAt(level) == '#') {
            level++;
        }
        if (level < 1 || level > 6 || level >= trimmed.length() || trimmed.charAt(level) != ' ') {
            return null;
        }
        String title = trimmed.substring(level).trim();
        return title.isBlank() ? null : new Heading(level, title);
    }

    private String buildPath(String[] headings, String fallback) {
        List<String> parts = new ArrayList<>();
        for (String heading : headings) {
            if (heading != null && !heading.isBlank()) {
                parts.add(heading);
            }
        }
        return parts.isEmpty() ? fallback : String.join(" > ", parts);
    }

    private String stripExtension(String fileName) {
        int dot = fileName.lastIndexOf('.');
        return dot > 0 ? fileName.substring(0, dot) : fileName;
    }

    private record Heading(int level, String title) {
    }

    private record Section(String sectionPath, String content) {
    }
}
