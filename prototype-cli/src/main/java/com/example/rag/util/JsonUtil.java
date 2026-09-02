package com.example.rag.util;

import java.util.ArrayList;
import java.util.List;

public final class JsonUtil {
    private JsonUtil() {
    }

    public static String quote(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder(value.length() + 16);
        out.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        out.append('"');
        return out.toString();
    }

    public static String array(List<String> values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) {
                out.append(',');
            }
            out.append(quote(values.get(i)));
        }
        return out.append(']').toString();
    }

    public static String extractString(String json, String key) {
        int keyPos = json.indexOf('"' + key + '"');
        if (keyPos < 0) {
            return "";
        }
        int colon = json.indexOf(':', keyPos);
        if (colon < 0) {
            return "";
        }
        int start = json.indexOf('"', colon + 1);
        if (start < 0) {
            return "";
        }
        StringBuilder value = new StringBuilder();
        boolean escaping = false;
        for (int i = start + 1; i < json.length(); i++) {
            char c = json.charAt(i);
            if (escaping) {
                switch (c) {
                    case '"' -> value.append('"');
                    case '\\' -> value.append('\\');
                    case '/' -> value.append('/');
                    case 'b' -> value.append('\b');
                    case 'f' -> value.append('\f');
                    case 'n' -> value.append('\n');
                    case 'r' -> value.append('\r');
                    case 't' -> value.append('\t');
                    case 'u' -> {
                        if (i + 4 < json.length()) {
                            String hex = json.substring(i + 1, i + 5);
                            value.append((char) Integer.parseInt(hex, 16));
                            i += 4;
                        }
                    }
                    default -> value.append(c);
                }
                escaping = false;
            } else if (c == '\\') {
                escaping = true;
            } else if (c == '"') {
                return value.toString();
            } else {
                value.append(c);
            }
        }
        return value.toString();
    }

    public static int extractInt(String json, String key) {
        String value = extractRawScalar(json, key);
        if (value.isBlank()) {
            return 0;
        }
        return Integer.parseInt(value);
    }

    public static double extractDouble(String json, String key) {
        String value = extractRawScalar(json, key);
        if (value.isBlank()) {
            return 0.0;
        }
        return Double.parseDouble(value);
    }

    public static boolean extractBoolean(String json, String key) {
        return Boolean.parseBoolean(extractRawScalar(json, key));
    }

    public static List<String> extractStringArray(String json, String key) {
        int keyPos = json.indexOf('"' + key + '"');
        if (keyPos < 0) {
            return List.of();
        }
        int start = json.indexOf('[', keyPos);
        int end = json.indexOf(']', start);
        if (start < 0 || end < 0) {
            return List.of();
        }
        String body = json.substring(start + 1, end);
        List<String> values = new ArrayList<>();
        int pos = 0;
        while (pos < body.length()) {
            int quote = body.indexOf('"', pos);
            if (quote < 0) {
                break;
            }
            int next = quote + 1;
            boolean escaping = false;
            while (next < body.length()) {
                char c = body.charAt(next);
                if (escaping) {
                    escaping = false;
                } else if (c == '\\') {
                    escaping = true;
                } else if (c == '"') {
                    break;
                }
                next++;
            }
            values.add(extractString("{\"v\":" + body.substring(quote, Math.min(next + 1, body.length())) + "}", "v"));
            pos = next + 1;
        }
        return values;
    }

    private static String extractRawScalar(String json, String key) {
        int keyPos = json.indexOf('"' + key + '"');
        if (keyPos < 0) {
            return "";
        }
        int colon = json.indexOf(':', keyPos);
        if (colon < 0) {
            return "";
        }
        int start = colon + 1;
        while (start < json.length() && Character.isWhitespace(json.charAt(start))) {
            start++;
        }
        int end = start;
        while (end < json.length()) {
            char c = json.charAt(end);
            if (c == ',' || c == '}') {
                break;
            }
            end++;
        }
        return json.substring(start, end).trim();
    }
}
