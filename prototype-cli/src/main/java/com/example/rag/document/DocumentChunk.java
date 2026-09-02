package com.example.rag.document;

import com.example.rag.util.JsonUtil;

public record DocumentChunk(
        String chunkId,
        String sourceName,
        String sourceRoot,
        String sourcePath,
        String fileName,
        String sectionPath,
        int chunkIndex,
        String docType,
        String content,
        int contentLength
) {
    public String toJson() {
        return "{"
                + "\"chunk_id\":" + JsonUtil.quote(chunkId)
                + ",\"source_name\":" + JsonUtil.quote(sourceName)
                + ",\"source_root\":" + JsonUtil.quote(sourceRoot)
                + ",\"source_path\":" + JsonUtil.quote(sourcePath)
                + ",\"file_name\":" + JsonUtil.quote(fileName)
                + ",\"section_path\":" + JsonUtil.quote(sectionPath)
                + ",\"chunk_index\":" + chunkIndex
                + ",\"doc_type\":" + JsonUtil.quote(docType)
                + ",\"content\":" + JsonUtil.quote(content)
                + ",\"content_length\":" + contentLength
                + "}";
    }

    public static DocumentChunk fromJson(String json) {
        return new DocumentChunk(
                JsonUtil.extractString(json, "chunk_id"),
                JsonUtil.extractString(json, "source_name"),
                JsonUtil.extractString(json, "source_root"),
                JsonUtil.extractString(json, "source_path"),
                JsonUtil.extractString(json, "file_name"),
                JsonUtil.extractString(json, "section_path"),
                JsonUtil.extractInt(json, "chunk_index"),
                JsonUtil.extractString(json, "doc_type"),
                JsonUtil.extractString(json, "content"),
                JsonUtil.extractInt(json, "content_length")
        );
    }
}
