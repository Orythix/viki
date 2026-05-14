package com.viki.qalab;

/**
 * Environment-driven settings (mirror Python {@code qa_lab.config}).
 * Security: never log {@link #apiKey()} in production reporters.
 */
public final class LabConfig {

    private LabConfig() {}

    public static String baseUrl() {
        return stripTrailingSlash(firstNonBlank(System.getenv("QA_BASE_URL"), "http://127.0.0.1:8000"));
    }

    public static String apiKey() {
        return firstNonBlank(System.getenv("QA_API_KEY"), "dev-lab-change-me");
    }

    public static String role() {
        return firstNonBlank(System.getenv("QA_LAB_ROLE"), "lab_admin");
    }

    static String stripTrailingSlash(String url) {
        if (url == null || url.isEmpty()) {
            return "http://127.0.0.1:8000";
        }
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }

    private static String firstNonBlank(String v, String dflt) {
        if (v == null || v.isBlank()) {
            return dflt;
        }
        return v.trim();
    }
}
