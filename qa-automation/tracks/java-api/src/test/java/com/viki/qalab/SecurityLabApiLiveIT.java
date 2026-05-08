package com.viki.qalab;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/**
 * Live API checks — disabled in CI unless QA_LIVE_JAVA=1 (same idea as Python {@code @pytest.mark.live}).
 */
@EnabledIfEnvironmentVariable(named = "QA_LIVE_JAVA", matches = "1")
class SecurityLabApiLiveIT {

    @Test
    @DisplayName("GET /health returns ok")
    void healthOk() {
        given()
                .baseUri(LabConfig.baseUrl())
                .when()
                .get("/health")
                .then()
                .statusCode(200)
                .body("status", equalTo("ok"));
    }

    @Test
    @DisplayName("GET /api/v1/metrics requires API key")
    void metricsRequiresKey() {
        given()
                .baseUri(LabConfig.baseUrl())
                .when()
                .get("/api/v1/metrics")
                .then()
                .statusCode(401);
    }
}
