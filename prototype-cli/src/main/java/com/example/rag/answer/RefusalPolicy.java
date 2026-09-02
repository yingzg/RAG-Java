package com.example.rag.answer;

import com.example.rag.retrieval.SearchResult;

import java.util.List;
import java.util.Set;

public class RefusalPolicy {
    private static final double MIN_TOP_SCORE = 8.0;
    private static final Set<String> SENSITIVE_TERMS = Set.of(
            "密码", "密钥", "token", "cookie", "secret", "生产数据库密码", "accesskey", "ak", "sk"
    );

    public boolean shouldRefuse(String question, List<SearchResult> results) {
        String lower = question.toLowerCase(java.util.Locale.ROOT);
        for (String term : SENSITIVE_TERMS) {
            if (lower.contains(term.toLowerCase(java.util.Locale.ROOT))) {
                return true;
            }
        }
        return results.isEmpty() || results.get(0).score() < MIN_TOP_SCORE;
    }

    public String reason(String question, List<SearchResult> results) {
        String lower = question.toLowerCase(java.util.Locale.ROOT);
        for (String term : SENSITIVE_TERMS) {
            if (lower.contains(term.toLowerCase(java.util.Locale.ROOT))) {
                return "问题疑似请求敏感信息或生产凭据，Day1 RAG 默认拒答。";
            }
        }
        if (results.isEmpty()) {
            return "没有检索到相关文档片段。";
        }
        return "最高检索分 " + String.format(java.util.Locale.ROOT, "%.2f", results.get(0).score())
                + " 低于 Day1 证据阈值。";
    }
}
