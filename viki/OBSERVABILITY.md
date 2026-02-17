# Observability Enhancement Plan

**Last updated:** 2026-02-17

## Current State

The VIKI system has basic logging through `viki_logger` but lacks:
- Structured logging (JSON format)
- Request tracing with correlation IDs
- Metrics export (Prometheus, OpenTelemetry)
- Performance monitoring for layers
- Error rate tracking per skill

## Proposed Enhancements

### 1. Structured Logging

**Goal:** Enable log aggregation and analysis with tools like ELK, Splunk, or CloudWatch.

**Implementation:**
```python
# viki/config/logger.py
import logging
import json
import sys
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logs."""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'skill'):
            log_data['skill'] = record.skill
        if hasattr(record, 'latency_ms'):
            log_data['latency_ms'] = record.latency_ms
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

# Usage
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StructuredFormatter())
viki_logger.addHandler(handler)
```

### 2. Request Tracing

**Goal:** Track requests through the entire processing pipeline.

**Implementation:**
```python
import uuid
from contextvars import ContextVar

# Context variable for request ID (thread-safe for async)
request_id_var: ContextVar[str] = ContextVar('request_id', default=None)

class RequestTracer:
    """Manages request tracing through the system."""
    
    def __init__(self):
        self.active_traces = {}
    
    def start_trace(self, user_input: str) -> str:
        """Start a new request trace."""
        trace_id = str(uuid.uuid4())
        request_id_var.set(trace_id)
        
        self.active_traces[trace_id] = {
            'trace_id': trace_id,
            'start_time': time.time(),
            'user_input': user_input[:100],
            'stages': [],
        }
        
        viki_logger.info("Request started", extra={
            'request_id': trace_id,
            'input_preview': user_input[:100]
        })
        
        return trace_id
    
    def log_stage(self, stage_name: str, duration_ms: float):
        """Log a pipeline stage completion."""
        trace_id = request_id_var.get()
        if trace_id and trace_id in self.active_traces:
            self.active_traces[trace_id]['stages'].append({
                'stage': stage_name,
                'duration_ms': duration_ms,
                'timestamp': time.time()
            })
            
            viki_logger.info(f"Stage completed: {stage_name}", extra={
                'request_id': trace_id,
                'stage': stage_name,
                'latency_ms': duration_ms
            })
    
    def end_trace(self, success: bool = True):
        """Complete a request trace."""
        trace_id = request_id_var.get()
        if trace_id and trace_id in self.active_traces:
            trace = self.active_traces[trace_id]
            total_duration = (time.time() - trace['start_time']) * 1000
            
            viki_logger.info("Request completed", extra={
                'request_id': trace_id,
                'total_latency_ms': total_duration,
                'success': success,
                'stage_count': len(trace['stages'])
            })
            
            del self.active_traces[trace_id]
            request_id_var.set(None)

# Usage in controller
tracer = RequestTracer()

async def process_request(self, user_input: str) -> str:
    trace_id = tracer.start_trace(user_input)
    
    try:
        # Process stages...
        start = time.time()
        # ... stage execution ...
        tracer.log_stage("reflex", (time.time() - start) * 1000)
        
        # ... more stages ...
        
        tracer.end_trace(success=True)
        return response
    except Exception as e:
        tracer.end_trace(success=False)
        raise
```

### 3. Metrics Export

**Goal:** Export metrics to Prometheus or OpenTelemetry for monitoring.

**Dependencies:**
```bash
pip install prometheus-client opentelemetry-api opentelemetry-sdk
```

**Implementation:**
```python
# viki/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time

class VIKIMetrics:
    """Prometheus metrics for VIKI."""
    
    def __init__(self):
        # Request metrics
        self.requests_total = Counter(
            'viki_requests_total',
            'Total number of requests',
            ['status']  # success, error, blocked
        )
        
        self.request_duration = Histogram(
            'viki_request_duration_seconds',
            'Request processing duration',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )
        
        # Skill metrics
        self.skill_executions = Counter(
            'viki_skill_executions_total',
            'Total skill executions',
            ['skill_name', 'status']
        )
        
        self.skill_duration = Histogram(
            'viki_skill_duration_seconds',
            'Skill execution duration',
            ['skill_name'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        )
        
        # System metrics
        self.active_requests = Gauge(
            'viki_active_requests',
            'Number of currently processing requests'
        )
        
        self.cortex_layer_duration = Histogram(
            'viki_cortex_layer_duration_seconds',
            'Cortex layer processing duration',
            ['layer_name'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
        )
    
    def start_server(self, port: int = 9090):
        """Start Prometheus metrics HTTP server."""
        start_http_server(port)
        viki_logger.info(f"Metrics server started on port {port}")

# Usage
metrics = VIKIMetrics()
metrics.start_server(port=9090)

# In controller
@metrics.active_requests.track_inprogress()
async def process_request(self, user_input: str) -> str:
    start_time = time.time()
    
    try:
        # ... processing ...
        
        metrics.requests_total.labels(status='success').inc()
        return response
    except Exception as e:
        metrics.requests_total.labels(status='error').inc()
        raise
    finally:
        duration = time.time() - start_time
        metrics.request_duration.observe(duration)

# In skill execution
start_time = time.time()
try:
    result = await skill.execute(params)
    metrics.skill_executions.labels(skill_name=skill_name, status='success').inc()
    return result
except Exception as e:
    metrics.skill_executions.labels(skill_name=skill_name, status='error').inc()
    raise
finally:
    duration = time.time() - start_time
    metrics.skill_duration.labels(skill_name=skill_name).observe(duration)
```

### 4. Performance Dashboard

**Goal:** Visualize system performance in real-time.

**Tools:**
- Prometheus for metrics collection
- Grafana for visualization
- Pre-built dashboard templates

**Key Metrics to Track:**
1. Request throughput (requests/second)
2. Average response time
3. P50, P95, P99 latencies
4. Error rate
5. Skill execution times
6. Cortex layer performance
7. Memory usage
8. Active connections

**Sample Grafana Dashboard JSON:**
```json
{
  "dashboard": {
    "title": "VIKI Performance",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(viki_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Average Response Time",
        "targets": [
          {
            "expr": "rate(viki_request_duration_seconds_sum[5m]) / rate(viki_request_duration_seconds_count[5m])"
          }
        ]
      }
    ]
  }
}
```

### 5. Error Tracking

**Goal:** Capture and aggregate errors for analysis.

**Implementation:**
```python
class ErrorTracker:
    """Tracks and categorizes errors."""
    
    def __init__(self):
        self.error_counts = {}
        self.recent_errors = []
    
    def record_error(self, error_type: str, message: str, context: Dict):
        """Record an error occurrence."""
        key = f"{error_type}:{message[:50]}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
        
        self.recent_errors.append({
            'timestamp': time.time(),
            'type': error_type,
            'message': message,
            'context': context
        })
        
        # Keep only last 100 errors
        if len(self.recent_errors) > 100:
            self.recent_errors.pop(0)
        
        # Log structured error
        viki_logger.error(f"Error: {error_type}", extra={
            'error_type': error_type,
            'error_message': message,
            **context
        })
    
    def get_error_summary(self) -> Dict:
        """Get summary of recent errors."""
        return {
            'total_types': len(self.error_counts),
            'most_common': sorted(self.error_counts.items(), 
                                key=lambda x: x[1], reverse=True)[:5],
            'recent_count': len(self.recent_errors)
        }
```

## Implementation Plan

**Phase 1 (Week 1):**
- Add structured logging formatter
- Implement request ID generation
- Update critical log points with extra fields

**Phase 2 (Week 2):**
- Add RequestTracer class
- Integrate tracing into controller pipeline
- Add stage timing

**Phase 3 (Week 3):**
- Set up Prometheus metrics
- Add counters and histograms
- Start metrics HTTP server

**Phase 4 (Week 4):**
- Create Grafana dashboard
- Set up alerts for errors/high latency
- Document monitoring procedures

## Configuration

**Environment Variables:**
```bash
# Logging
VIKI_LOG_LEVEL=INFO
VIKI_LOG_FORMAT=json  # json or text

# Metrics
VIKI_METRICS_ENABLED=true
VIKI_METRICS_PORT=9090

# Tracing
VIKI_TRACING_ENABLED=true
VIKI_TRACE_SAMPLE_RATE=1.0  # 0.0 to 1.0
```

## Benefits

1. **Faster Debugging:** Structured logs make it easy to find issues
2. **Performance Insights:** Identify bottlenecks in real-time
3. **Proactive Monitoring:** Alerts before users notice problems
4. **Capacity Planning:** Understand usage patterns and scale accordingly
5. **Audit Trail:** Complete request history for compliance

## Notes

- Start with structured logging (lowest effort, high value)
- Add metrics incrementally per module
- Consider log aggregation costs in production
- Use sampling for high-volume trace data
