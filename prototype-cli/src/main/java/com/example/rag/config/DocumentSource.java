package com.example.rag.config;

import java.nio.file.Path;

public record DocumentSource(String name, Path root, String description) {
}
