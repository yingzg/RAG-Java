package com.example.rag.trace;

import com.example.rag.util.TextUtil;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;

public class TraceRecorder {
    private final Path traceDir;

    public TraceRecorder(Path traceDir) {
        this.traceDir = traceDir;
    }

    public String nextTraceId(String seed) {
        return "trace_" + Instant.now().toString().replaceAll("[-:.TZ]", "") + "_" + TextUtil.sha1Short(seed);
    }

    public void record(RagTrace trace) throws IOException {
        Files.createDirectories(traceDir);
        Path file = traceDir.resolve(trace.traceId() + ".json");
        Files.writeString(file, trace.toJson() + System.lineSeparator(), StandardCharsets.UTF_8);
    }

    public Path traceDir() {
        return traceDir;
    }
}
