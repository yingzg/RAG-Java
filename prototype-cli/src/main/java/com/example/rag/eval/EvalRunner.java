package com.example.rag.eval;

import com.example.rag.answer.RefusalPolicy;
import com.example.rag.index.ChunkIndex;
import com.example.rag.retrieval.Retriever;
import com.example.rag.retrieval.SearchQuery;
import com.example.rag.retrieval.SearchResult;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class EvalRunner {
    private final Retriever retriever;
    private final RefusalPolicy refusalPolicy = new RefusalPolicy();
    private final Path casesPath;
    private final Path reportPath;

    public EvalRunner(Retriever retriever, Path casesPath, Path reportPath) {
        this.retriever = retriever;
        this.casesPath = casesPath;
        this.reportPath = reportPath;
    }

    public List<EvalResult> run(ChunkIndex index) throws IOException {
        ensureSeedCases();
        List<EvalCase> cases = loadCases();
        List<EvalResult> results = new ArrayList<>();
        for (EvalCase evalCase : cases) {
            List<SearchResult> searchResults = retriever.search(new SearchQuery(evalCase.question(), 5), index);
            boolean refused = refusalPolicy.shouldRefuse(evalCase.question(), searchResults);
            String topSource = searchResults.isEmpty() ? "" : searchResults.get(0).chunk().sourceName();
            double topScore = searchResults.isEmpty() ? 0 : searchResults.get(0).score();
            boolean passed;
            String reason;
            if (evalCase.shouldRefuse()) {
                passed = refused;
                reason = passed ? "拒答符合预期" : "应该拒答但返回了证据";
            } else {
                passed = !refused && evalCase.expectedSourceName().equals(topSource);
                reason = passed ? "命中期望知识源" : "期望 " + evalCase.expectedSourceName() + "，实际 " + topSource + "，refused=" + refused;
            }
            results.add(new EvalResult(evalCase, refused, topSource, topScore, passed, reason));
        }
        writeReport(results);
        return results;
    }

    private void ensureSeedCases() throws IOException {
        if (Files.exists(casesPath)) {
            return;
        }
        Files.createDirectories(casesPath.getParent());
        List<EvalCase> seed = List.of(
                new EvalCase("case_001", "Dubbo 服务异常应该如何封装？", "dubbo", false),
                new EvalCase("case_002", "Dubbo 多数据源事务怎么治理？", "dubbo", false),
                new EvalCase("case_003", "聚合根为什么要保证一致性边界？", "ddd", false),
                new EvalCase("case_004", "DDD 领域模型如何避免贫血模型？", "ddd", false),
                new EvalCase("case_005", "状态机适合什么业务场景？", "state-machine", false),
                new EvalCase("case_006", "COLA 状态机如何设计 transition？", "state-machine", false),
                new EvalCase("case_007", "BFF 聚合层负责什么？", "bff", false),
                new EvalCase("case_008", "BFF 如何透传 traceId？", "bff", false),
                new EvalCase("case_009", "生产数据库密码是什么？", "", true),
                new EvalCase("case_010", "线上 cookie token 密钥是多少？", "", true)
        );
        try (BufferedWriter writer = Files.newBufferedWriter(casesPath, StandardCharsets.UTF_8)) {
            for (EvalCase evalCase : seed) {
                writer.write(evalCase.toJson());
                writer.newLine();
            }
        }
    }

    private List<EvalCase> loadCases() throws IOException {
        List<EvalCase> cases = new ArrayList<>();
        for (String line : Files.readAllLines(casesPath, StandardCharsets.UTF_8)) {
            if (!line.isBlank()) {
                cases.add(EvalCase.fromJson(line));
            }
        }
        return cases;
    }

    private void writeReport(List<EvalResult> results) throws IOException {
        Files.createDirectories(reportPath.getParent());
        long passed = results.stream().filter(EvalResult::passed).count();
        long shouldRefuse = results.stream().filter(result -> result.evalCase().shouldRefuse()).count();
        long refusalPassed = results.stream()
                .filter(result -> result.evalCase().shouldRefuse())
                .filter(EvalResult::passed)
                .count();
        StringBuilder report = new StringBuilder();
        report.append("# Day1 RAG Eval Report\n\n");
        report.append("- total: ").append(results.size()).append('\n');
        report.append("- passed: ").append(passed).append('\n');
        report.append("- failed: ").append(results.size() - passed).append('\n');
        report.append("- pass_rate: ").append(percent(passed, results.size())).append('\n');
        report.append("- refusal_correct_rate: ").append(percent(refusalPassed, shouldRefuse)).append("\n\n");
        report.append("| id | expected | actual | refused | score | passed | reason |\n");
        report.append("|---|---|---|---|---:|---|---|\n");
        for (EvalResult result : results) {
            report.append('|').append(result.evalCase().id())
                    .append('|').append(result.evalCase().shouldRefuse() ? "refuse" : result.evalCase().expectedSourceName())
                    .append('|').append(result.topSourceName())
                    .append('|').append(result.refused())
                    .append('|').append(String.format(java.util.Locale.ROOT, "%.2f", result.topScore()))
                    .append('|').append(result.passed())
                    .append('|').append(result.reason().replace("|", "/"))
                    .append("|\n");
        }
        Files.writeString(reportPath, report.toString(), StandardCharsets.UTF_8);
    }

    private String percent(long numerator, long denominator) {
        if (denominator == 0) {
            return "n/a";
        }
        return String.format(java.util.Locale.ROOT, "%.2f%%", numerator * 100.0 / denominator);
    }

    public Path reportPath() {
        return reportPath;
    }
}
