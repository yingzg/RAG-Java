package com.example.rag.config;

import com.example.rag.util.JsonUtil;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SourceConfigLoader {
    private static final Pattern WSL_MOUNT_PATH = Pattern.compile("^/mnt/([a-zA-Z])/(.*)$");
    private static final Pattern WINDOWS_DRIVE_PATH = Pattern.compile("^([a-zA-Z]):[\\\\/](.*)$");

    public List<DocumentSource> load(Path configPath) throws IOException {
        String json = Files.readString(configPath, StandardCharsets.UTF_8);
        List<DocumentSource> sources = new ArrayList<>();
        int pos = 0;
        while (true) {
            int start = json.indexOf('{', pos);
            if (start < 0) {
                break;
            }
            int end = json.indexOf('}', start);
            if (end < 0) {
                break;
            }
            String object = json.substring(start, end + 1);
            String name = JsonUtil.extractString(object, "name");
            String root = JsonUtil.extractString(object, "root");
            String description = JsonUtil.extractString(object, "description");
            if (!name.isBlank() && !root.isBlank()) {
                sources.add(new DocumentSource(name, resolvePortablePath(root), description));
            }
            pos = end + 1;
        }
        return sources;
    }

    private Path resolvePortablePath(String configuredRoot) {
        Path original = Path.of(configuredRoot);
        if (Files.isDirectory(original)) {
            return original;
        }

        Matcher wslPath = WSL_MOUNT_PATH.matcher(configuredRoot);
        if (wslPath.matches()) {
            String drive = wslPath.group(1).toUpperCase(Locale.ROOT);
            String rest = wslPath.group(2).replace('/', '\\');
            Path windowsPath = Path.of(drive + ":\\" + rest);
            if (Files.isDirectory(windowsPath)) {
                return windowsPath;
            }
        }

        Matcher windowsPath = WINDOWS_DRIVE_PATH.matcher(configuredRoot);
        if (windowsPath.matches()) {
            String drive = windowsPath.group(1).toLowerCase(Locale.ROOT);
            String rest = windowsPath.group(2).replace('\\', '/');
            Path wslMountPath = Path.of("/mnt/" + drive + "/" + rest);
            if (Files.isDirectory(wslMountPath)) {
                return wslMountPath;
            }
        }

        return original;
    }
}
