# Technical Specification: VIKI Observability Stack Implementation

**Pillar:** Operational Excellence & Safety
**Goal:** Implement a comprehensive, real-time observability stack for VIKI to provide deep visibility into agent performance, latency, and failure modes across all core components.
**Target Audience:** Engineering Team (Backend/DevOps)
**Status:** Draft - Ready for Review

---

## 1. Instrumentation Strategy: Key Points for Logging & Tracing

The instrumentation must adopt a distributed tracing approach to track the full lifecycle of a user request, from entry point to final response generation. We will use **OpenTelemetry (OTel)** as the standard framework.

### A. Core Request Lifecycle Tracing
Every incoming request must be wrapped in a single trace ID (`trace_id`) and span ID (`span_id`).

*   **`process_request` (Controller):**
    *   **Start Span:** Record the start time of processing the request.
    *   **Span 1: Input Validation/Pre-processing:** Log input parameters, user context, and initial validation status.
    *   **Span 2: Orchestration/Planning:** Trace the logic flow (e.g., deciding which skills to use).
    *   **Span 3: Skill Execution Loop:** This is the critical section. Each call to a skill or tool must be its own child span.
        *   *Before Tool Call:* Log the selected tool name, input arguments, and expected output schema.
        *   *After Tool Call:* Log the actual execution time and success/failure status of the tool.
    *   **Span 4: LLM Interaction:** Wrap all calls to external LLMs (e.g., OpenAI, local models). Record model name, prompt length, token usage, and API latency.
    *   **End Span:** Calculate total request duration and log final success/failure status.

### B. Component-Specific Instrumentation Points

| Component | Key Action Point | Metric/Log Data to Capture | Purpose |
| :--- | :--- | :--- | :--- |
| **Controller** | `process_request` entry/exit | Total duration, initial error type. | Overall system health and throughput. |
| **SkillExecutor** | Tool execution start/end | Skill name, input arguments, execution time, return value schema validation errors. | Identifying bottlenecks or unreliable skills. |
| **KnowledgeIngestor** | Ingestion pipeline stages | Source document count, chunking rate, embedding model latency, vector store write success rate. | Monitoring data freshness and ingestion throughput. |
| **LLM Calls** | API request/response cycle | Model name, prompt length (tokens), response tokens, API latency (network time). | Cost tracking and identifying LLM performance degradation. |

---

## 2. Technology Stack Recommendation & Justification

We recommend a modern, vendor-neutral stack built around open standards to ensure flexibility and avoid vendor lock-in.

### A. Core Observability Tools
1.  **Tracing:** **OpenTelemetry (OTel)**.
    *   *Justification:* OTel is the industry standard for instrumenting distributed systems. It provides a unified set of APIs, SDKs, and specifications to generate telemetry data (traces, metrics, logs) that can be exported to multiple backends without changing application code significantly.
2.  **Metrics:** **Prometheus**.
    *   *Justification:* Excellent for time-series data collection and alerting. It uses a pull model (`/metrics` endpoint), which is simple to implement in existing services (Controller, SkillExecutor) and integrates well with modern container orchestration (Kubernetes).
3.  **Logging:** **ELK Stack (Elasticsearch, Logstash, Kibana)** or **Loki**.
    *   *Recommendation:* Given the complexity of agent logs, a centralized logging system is mandatory. We recommend **Grafana Loki** paired with Promtail/Prometheus for its cost-effectiveness and strong integration with Prometheus metrics, allowing us to query logs based on metric labels (e.g., "Show me all errors for `skill_name=ToolX` where `latency > 500ms`").

### B. Data Flow Architecture
1.  **Application Code $\rightarrow$ OTel SDK:** Instrument code generates spans and metrics using the OTel Python/Language SDK.
2.  **OTel Collector:** A dedicated sidecar or service collects all raw telemetry data (traces, metrics, logs) from the services. This decouples instrumentation from backend concerns.
3.  **Backend Storage:** The Collector exports data to:
    *   **Jaeger/Tempo:** For storing and querying traces.
    *   **Prometheus/Mimir:** For time-series metrics.
    *   **Loki/Elasticsearch:** For structured logs.

---

## 3. Implementation Components & Modifications

The implementation requires creating a dedicated observability layer that wraps core business logic components.

### A. New Service: `viki/observability/tracer.py` (or similar)
This module will encapsulate all OTel initialization and context management. It should provide simple decorators or context managers for developers to use:

```python
# Example usage in Controller
from viki.observability.tracer import trace_request

@trace_request(service="Controller", operation="process_request")
def process_request(user_input):
    # ... core logic ...
```

### B. Modifications to Existing Services

1.  **`viki/core/controller.py` (Controller):**
    *   Wrap the main request handling method with the new tracing decorator (`@trace_request`).
    *   Implement metric collection for overall success rate and total latency using Prometheus client libraries.
2.  **`viki/executor/skill_executor.py` (SkillExecutor):**
    *   Modify `execute_tool(tool_name, args)`: This function must be wrapped to capture the tool's execution time and status code as a child span within the main request trace.
3.  **`viki/ingestor/knowledge_ingestor.py` (KnowledgeIngestor):**
    *   Instrument key steps: Document loading $\rightarrow$ Chunking $\rightarrow$ Embedding Generation $\rightarrow$ Vector Store Write. Each step should be a distinct span to pinpoint data pipeline failures.

### C. Infrastructure Changes
1.  **Deployment:** Update `docker-compose.yml` and `Dockerfile` to include the **OpenTelemetry Collector** as a sidecar container or dedicated service.
2.  **Configuration:** Create/update `config/observability.yaml` to manage endpoints for Jaeger, Prometheus, and Loki.

---

## 4. Metrics Definition (KPIs)

Metrics must be categorized into four groups: Performance, Reliability, Resource Utilization, and Business Logic.

### A. Latency Metrics (Time-based)
*   **Metric:** `viki_request_duration_seconds` (Histogram/Summary)
    *   **Labels:** `service`, `operation`, `status` (success/failure).
    *   **KPIs to Track:** P50, P95, P99 latency for the entire request lifecycle.
*   **Metric:** `viki_llm_call_latency_seconds` (Histogram)
    *   **Labels:** `model`, `operation`.

### B. Reliability Metrics (Success/Failure Rate)
*   **Metric:** `viki_skill_execution_total` (Counter)
    *   **Labels:** `service`, `skill_name`, `status` (success, failure).
    *   **KPIs to Track:** Success rate per skill. Alerts should trigger if the success rate for a critical skill drops below 95%.
*   **Metric:** `viki_request_error_total` (Counter)
    *   **Labels:** `service`, `error_type` (e.g., `LLM_API_ERROR`, `TOOL_TIMEOUT`, `VALIDATION_ERROR`).

### C. Resource Utilization Metrics (System Health)
These should be collected by Prometheus Node Exporters and scraped from the host/container runtime:
*   **Metric:** `process_cpu_seconds_total`
*   **Metric:** `process_resident_memory_bytes`

### D. Business Logic Metrics (Domain Specific)
*   **Metric:** `viki_knowledge_ingestion_count` (Counter)
    *   **Labels:** `source_type`, `status`.
    *   **KPIs to Track:** Number of documents successfully ingested per hour/day.

---
***Next Steps:***
1.  Implement the OTel SDK wrapper in core components (`Controller`, `SkillExecutor`).
2.  Deploy and configure the OpenTelemetry Collector sidecar.
3.  Define Prometheus exporters for all required metrics.