package com.example.rag.eval;

public record EvalResult(
        EvalCase evalCase,
        boolean refused,
        String topSourceName,
        double topScore,
        boolean passed,
        String reason
) {
}
