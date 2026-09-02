package com.example.rag.eval;

import com.example.rag.util.JsonUtil;

public record EvalCase(
        String id,
        String question,
        String expectedSourceName,
        boolean shouldRefuse
) {
    public String toJson() {
        return "{"
                + "\"id\":" + JsonUtil.quote(id)
                + ",\"question\":" + JsonUtil.quote(question)
                + ",\"expected_source_name\":" + JsonUtil.quote(expectedSourceName)
                + ",\"should_refuse\":" + shouldRefuse
                + "}";
    }

    public static EvalCase fromJson(String json) {
        return new EvalCase(
                JsonUtil.extractString(json, "id"),
                JsonUtil.extractString(json, "question"),
                JsonUtil.extractString(json, "expected_source_name"),
                JsonUtil.extractBoolean(json, "should_refuse")
        );
    }
}
