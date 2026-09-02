package com.example.rag.document;

public class MetadataExtractor {
    public String docType(String sourcePath) {
        String path = sourcePath.replace('\\', '/');
        if (path.contains("00-索引")) {
            return "index";
        }
        if (path.contains("源码深度版")) {
            return "deep_dive";
        }
        if (path.contains("重建指南")) {
            return "rebuild_guide";
        }
        if (path.contains("面试")) {
            return "interview";
        }
        if (path.contains("关键类解剖") || path.contains("类-")) {
            return "class_analysis";
        }
        if (path.contains("入口级链路") || path.contains("示例项目解读") || path.contains("链路")) {
            return "call_chain";
        }
        if (path.toLowerCase().contains("readme")) {
            return "readme";
        }
        return "knowledge";
    }
}
