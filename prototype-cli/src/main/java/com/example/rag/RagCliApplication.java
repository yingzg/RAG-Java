package com.example.rag;

import com.example.rag.answer.AnswerBuilder;
import com.example.rag.answer.RagAnswer;
import com.example.rag.config.DocumentSource;
import com.example.rag.config.SourceConfigLoader;
import com.example.rag.eval.EvalResult;
import com.example.rag.eval.EvalRunner;
import com.example.rag.index.ChunkIndex;
import com.example.rag.index.IndexService;
import com.example.rag.index.JsonlChunkStore;
import com.example.rag.retrieval.KeywordRetriever;
import com.example.rag.retrieval.SearchQuery;
import com.example.rag.retrieval.SearchResult;
import com.example.rag.trace.RagTrace;
import com.example.rag.trace.TraceRecorder;
import com.example.rag.util.TextUtil;

import java.nio.file.Path;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;

public class RagCliApplication {
    private static final Path CONFIG_PATH = Path.of("config/sources.json");
    private static final Path INDEX_PATH = Path.of("data/index/chunks.jsonl");
    private static final Path TRACE_DIR = Path.of("data/traces");
    private static final Path EVAL_CASES_PATH = Path.of("data/eval/rag_cases.jsonl");
    private static final Path EVAL_REPORT_PATH = Path.of("data/eval/rag_eval_report.md");

    private final SourceConfigLoader sourceConfigLoader = new SourceConfigLoader();
    private final JsonlChunkStore chunkStore = new JsonlChunkStore(INDEX_PATH);
    private final KeywordRetriever retriever = new KeywordRetriever();
    private final TraceRecorder traceRecorder = new TraceRecorder(TRACE_DIR);
    private final AnswerBuilder answerBuilder = new AnswerBuilder();

    public static void main(String[] args) throws Exception {
        new RagCliApplication().run(args);
    }

    private void run(String[] args) throws Exception {
        if (args.length == 0 || "help".equalsIgnoreCase(args[0]) || "--help".equalsIgnoreCase(args[0])) {
            printHelp();
            return;
        }
        String command = args[0];
        switch (command) {
            case "index" -> index();
            case "search" -> search(args);
            case "answer" -> answer(args);
            case "eval" -> eval();
            default -> {
                System.err.println("Unknown command: " + command);
                printHelp();
                System.exit(2);
            }
        }
    }

    private void index() throws Exception {
        List<DocumentSource> sources = sourceConfigLoader.load(CONFIG_PATH);
        if (sources.isEmpty()) {
            throw new IllegalStateException("No sources configured in " + CONFIG_PATH.toAbsolutePath());
        }
        IndexService indexService = new IndexService(chunkStore);
        IndexService.IndexSummary summary = indexService.rebuild(sources);
        System.out.println("Index rebuilt.");
        System.out.println("Index path: " + summary.indexPath());
        System.out.println("Total chunks: " + summary.totalChunks());
        System.out.println("Documents by source:");
        summary.documentCounts().forEach((source, count) -> System.out.println("  - " + source + ": " + count));
        System.out.println("Chunks by source:");
        summary.chunkCounts().forEach((source, count) -> System.out.println("  - " + source + ": " + count));
    }

    private void search(String[] args) throws Exception {
        QueryArgs queryArgs = parseQueryArgs(args);
        long start = System.nanoTime();
        ChunkIndex index = loadRequiredIndex();
        List<SearchResult> results = retriever.search(new SearchQuery(queryArgs.question(), queryArgs.topK()), index);
        long latencyMs = elapsedMillis(start);
        String traceId = traceRecorder.nextTraceId("search|" + queryArgs.question());
        traceRecorder.record(new RagTrace(traceId, "search", queryArgs.question(), queryArgs.topK(), results, false, latencyMs, Instant.now()));

        System.out.println("trace_id: " + traceId);
        System.out.println("query: " + queryArgs.question());
        System.out.println("top_k: " + queryArgs.topK());
        System.out.println("latency_ms: " + latencyMs);
        System.out.println();
        printResults(results);
    }

    private void answer(String[] args) throws Exception {
        QueryArgs queryArgs = parseQueryArgs(args);
        long start = System.nanoTime();
        ChunkIndex index = loadRequiredIndex();
        List<SearchResult> results = retriever.search(new SearchQuery(queryArgs.question(), queryArgs.topK()), index);
        long latencyMs = elapsedMillis(start);
        String traceId = traceRecorder.nextTraceId("answer|" + queryArgs.question());
        RagAnswer answer = answerBuilder.build(traceId, queryArgs.question(), results);
        traceRecorder.record(new RagTrace(traceId, "answer", queryArgs.question(), queryArgs.topK(), results, answer.refused(), latencyMs, Instant.now()));

        System.out.println("trace_id: " + traceId);
        System.out.println("question: " + queryArgs.question());
        System.out.println("refused: " + answer.refused());
        System.out.println("latency_ms: " + latencyMs);
        System.out.println();
        System.out.println(answer.text());
        System.out.println("引用：");
        if (answer.refused() || answer.evidence().isEmpty()) {
            System.out.println("- 无");
        } else {
            for (SearchResult result : answer.evidence()) {
                System.out.println("- " + result.chunk().sourceName() + " / " + result.chunk().sourcePath()
                        + " > " + result.chunk().sectionPath() + " (score="
                        + String.format(java.util.Locale.ROOT, "%.2f", result.score()) + ")");
            }
        }
    }

    private void eval() throws Exception {
        ChunkIndex index = loadRequiredIndex();
        EvalRunner runner = new EvalRunner(retriever, EVAL_CASES_PATH, EVAL_REPORT_PATH);
        List<EvalResult> results = runner.run(index);
        long passed = results.stream().filter(EvalResult::passed).count();
        System.out.println("Eval complete.");
        System.out.println("total: " + results.size());
        System.out.println("passed: " + passed);
        System.out.println("failed: " + (results.size() - passed));
        System.out.println("report: " + runner.reportPath());
        for (EvalResult result : results) {
            System.out.println("- " + result.evalCase().id()
                    + " passed=" + result.passed()
                    + " expected=" + (result.evalCase().shouldRefuse() ? "refuse" : result.evalCase().expectedSourceName())
                    + " actual=" + result.topSourceName()
                    + " refused=" + result.refused()
                    + " score=" + String.format(java.util.Locale.ROOT, "%.2f", result.topScore())
                    + " reason=" + result.reason());
        }
    }

    private ChunkIndex loadRequiredIndex() throws Exception {
        ChunkIndex index = chunkStore.load();
        if (index.size() == 0) {
            throw new IllegalStateException("Index is empty. Run: java -jar target/rag-java-0.1.0.jar index");
        }
        return index;
    }

    private void printResults(List<SearchResult> results) {
        if (results.isEmpty()) {
            System.out.println("No matching chunks.");
            return;
        }
        int rank = 1;
        for (SearchResult result : results) {
            System.out.println("[" + rank++ + "] score=" + String.format(java.util.Locale.ROOT, "%.2f", result.score()));
            System.out.println("source: " + result.chunk().sourceName() + " / " + result.chunk().sourcePath());
            System.out.println("section: " + result.chunk().sectionPath());
            System.out.println("doc_type: " + result.chunk().docType());
            System.out.println("matched_terms: " + result.matchedTerms());
            System.out.println("preview: " + TextUtil.preview(result.chunk().content(), 260));
            System.out.println();
        }
    }

    private QueryArgs parseQueryArgs(String[] args) {
        if (args.length < 2) {
            throw new IllegalArgumentException("Missing question. Example: search \"Dubbo 服务异常应该如何封装？\"");
        }
        int topK = 5;
        StringBuilder question = new StringBuilder();
        for (int i = 1; i < args.length; i++) {
            if ("--topK".equals(args[i]) && i + 1 < args.length) {
                topK = Integer.parseInt(args[++i]);
            } else {
                if (question.length() > 0) {
                    question.append(' ');
                }
                question.append(args[i]);
            }
        }
        return new QueryArgs(question.toString(), topK);
    }

    private long elapsedMillis(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }

    private void printHelp() {
        System.out.println("RAG-Java Day1 CLI");
        System.out.println();
        System.out.println("Usage:");
        System.out.println("  java -jar target/rag-java-0.1.0.jar index");
        System.out.println("  java -jar target/rag-java-0.1.0.jar search \"Dubbo 服务异常应该如何封装？\" [--topK 5]");
        System.out.println("  java -jar target/rag-java-0.1.0.jar answer \"聚合根为什么要保证一致性边界？\" [--topK 5]");
        System.out.println("  java -jar target/rag-java-0.1.0.jar eval");
        System.out.println();
        System.out.println("Args: " + Arrays.toString(new String[] {"index", "search", "answer", "eval"}));
    }

    private record QueryArgs(String question, int topK) {
    }
}
