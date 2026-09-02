package com.example.rag.answer;

import com.example.rag.retrieval.SearchResult;
import com.example.rag.util.TextUtil;

import java.util.List;

public class AnswerBuilder {
    private final RefusalPolicy refusalPolicy = new RefusalPolicy();

    public RagAnswer build(String traceId, String question, List<SearchResult> results) {
        boolean refused = refusalPolicy.shouldRefuse(question, results);
        String text = refused ? refusalText(question, results) : answerText(results);
        return new RagAnswer(traceId, question, refused, text, results);
    }

    private String answerText(List<SearchResult> results) {
        StringBuilder out = new StringBuilder();
        out.append("结论：\n");
        out.append("根据当前知识库，以下片段与问题最相关。Day1 版本不调用 LLM，因此先输出证据摘要和引用；Day3 会升级为 LLM 基于证据生成答案。\n\n");
        out.append("相关依据：\n");
        int index = 1;
        for (SearchResult result : results) {
            out.append(index++).append(". ")
                    .append(result.chunk().sourceName()).append(" / ")
                    .append(result.chunk().sourcePath()).append(" > ")
                    .append(result.chunk().sectionPath()).append("\n");
            out.append("   score=")
                    .append(String.format(java.util.Locale.ROOT, "%.2f", result.score()))
                    .append(" matched=")
                    .append(result.matchedTerms())
                    .append("\n");
            out.append("   摘要：")
                    .append(TextUtil.preview(result.chunk().content(), 220))
                    .append("\n\n");
        }
        out.append("建议：\n");
        out.append("- 优先阅读上述引用文档确认规则原文。\n");
        out.append("- 如果需要自然语言完整总结，Day3 接入 LLM 后应继续强制基于这些引用回答。\n");
        return out.toString();
    }

    private String refusalText(String question, List<SearchResult> results) {
        return "根据当前知识库无法确认。\n\n"
                + "原因：\n"
                + refusalPolicy.reason(question, results)
                + "\n\n建议：\n"
                + "- 换一个更具体的问题，例如包含 Dubbo、DDD、状态机、BFF 等领域关键词。\n"
                + "- 或补充相关 Markdown 知识文档后重新执行 index。\n";
    }
}
