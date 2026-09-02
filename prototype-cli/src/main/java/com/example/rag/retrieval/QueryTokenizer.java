package com.example.rag.retrieval;

import com.example.rag.util.TextUtil;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QueryTokenizer {
    private static final Pattern ASCII_TOKEN = Pattern.compile("[A-Za-z][A-Za-z0-9_#.$-]*|[0-9]+");
    private static final Set<String> STOP_WORDS = Set.of(
            "什么", "如何", "为什么", "怎么", "一下", "介绍", "说明", "请问", "帮我", "这个", "那个",
            "是否", "可以", "应该", "需要", "进行", "问题", "知识", "文档"
    );

    public List<String> tokenize(String query) {
        String normalized = TextUtil.normalize(query);
        Set<String> tokens = new LinkedHashSet<>();
        Matcher matcher = ASCII_TOKEN.matcher(normalized);
        while (matcher.find()) {
            String token = matcher.group();
            if (token.length() >= 2) {
                tokens.add(token);
                tokens.add(token.toLowerCase(java.util.Locale.ROOT));
            }
        }
        String chineseOnly = normalized.replaceAll("[A-Za-z0-9_#.$-]+", " ").replaceAll("\\s+", "");
        addChineseNgrams(chineseOnly, 2, tokens);
        addChineseNgrams(chineseOnly, 3, tokens);
        tokens.removeIf(token -> token.isBlank() || STOP_WORDS.contains(token));
        return new ArrayList<>(tokens);
    }

    private void addChineseNgrams(String text, int size, Set<String> tokens) {
        if (text.length() < size) {
            if (!text.isBlank()) {
                tokens.add(text);
            }
            return;
        }
        for (int i = 0; i <= text.length() - size; i++) {
            String token = text.substring(i, i + size);
            if (!STOP_WORDS.contains(token)) {
                tokens.add(token);
            }
        }
    }
}
