package com.example.rag.retrieval;

import com.example.rag.document.DocumentChunk;
import com.example.rag.index.ChunkIndex;
import com.example.rag.util.TextUtil;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class KeywordRetriever implements Retriever {
    private final QueryTokenizer tokenizer = new QueryTokenizer();

    @Override
    public List<SearchResult> search(SearchQuery query, ChunkIndex index) {
        String normalizedQuery = TextUtil.oneLine(query.text());
        String lowerQuery = normalizedQuery.toLowerCase(Locale.ROOT);
        List<String> tokens = tokenizer.tokenize(normalizedQuery);
        List<SearchResult> results = new ArrayList<>();
        for (DocumentChunk chunk : index.chunks()) {
            SearchResult result = score(chunk, normalizedQuery, lowerQuery, tokens);
            if (result.score() > 0) {
                results.add(result);
            }
        }
        return results.stream()
                .sorted(Comparator.comparingDouble(SearchResult::score).reversed())
                .limit(query.topK())
                .toList();
    }

    private SearchResult score(DocumentChunk chunk, String query, String lowerQuery, List<String> tokens) {
        double score = 0;
        Set<String> matchedTerms = new LinkedHashSet<>();
        List<String> reasons = new ArrayList<>();
        String content = chunk.content();
        String lowerContent = content.toLowerCase(Locale.ROOT);
        String lowerSection = chunk.sectionPath().toLowerCase(Locale.ROOT);
        String lowerFileName = chunk.fileName().toLowerCase(Locale.ROOT);
        String lowerSource = chunk.sourceName().toLowerCase(Locale.ROOT);

        if (!query.isBlank() && lowerContent.contains(lowerQuery) && lowerQuery.length() >= 4) {
            score += 20;
            matchedTerms.add(query);
            reasons.add("完整问题短语命中正文 +20");
        }

        for (String token : tokens) {
            String lowerToken = token.toLowerCase(Locale.ROOT);
            int termHits = 0;
            if (lowerSection.contains(lowerToken)) {
                score += 8;
                termHits++;
                reasons.add(token + " 命中标题路径 +8");
            }
            if (lowerFileName.contains(lowerToken)) {
                score += 6;
                termHits++;
                reasons.add(token + " 命中文件名 +6");
            }
            if (lowerSource.contains(lowerToken)) {
                score += 5;
                termHits++;
                reasons.add(token + " 命中知识源 +5");
            }
            int contentHits = countOccurrences(lowerContent, lowerToken);
            if (contentHits > 0) {
                score += Math.min(12, contentHits * 2.0);
                termHits += contentHits;
                reasons.add(token + " 命中正文 " + contentHits + " 次 +" + Math.min(12, contentHits * 2));
            }
            if (termHits > 0) {
                matchedTerms.add(token);
            }
        }

        if ("deep_dive".equals(chunk.docType()) || "rebuild_guide".equals(chunk.docType())) {
            score += score > 0 ? 2 : 0;
        } else if ("index".equals(chunk.docType())) {
            score += score > 0 ? 1 : 0;
        }
        return new SearchResult(chunk, score, new ArrayList<>(matchedTerms), reasons);
    }

    private int countOccurrences(String text, String token) {
        if (token.isBlank()) {
            return 0;
        }
        int count = 0;
        int pos = 0;
        while (true) {
            int hit = text.indexOf(token, pos);
            if (hit < 0) {
                return count;
            }
            count++;
            pos = hit + token.length();
        }
    }
}
