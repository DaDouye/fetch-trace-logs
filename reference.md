







# Trace API Reference

## Jaeger Query API

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/traces/{traceID}` | GET | Get trace by ID |
| `/api/traces` | GET | Search traces |
| `/api/services` | GET | List all services |
| `/api/operations` | GET | List operations for a service |

### Search Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Service name (required) |
| `operation` | string | Operation name |
| `start` | timestamp | Start time (microseconds) |
| `end` | timestamp | End time (microseconds) |
| `tags` | string | Tags in JSON format |
| `limit` | integer | Maximum results |
| `minDuration` | string | Minimum span duration |
| `maxDuration` | string | Maximum span duration |

### Trace Structure

```json
{
  "traceID": "abc123",
  "spans": [
    {
      "spanID": "span001",
      "parentSpanID": "span000",
      "operationName": "GET /api/users",
      "startTime": 1704067200000000,
      "duration": 150000,
      "tags": [
        {"key": "http.method", "value": "GET"},
        {"key": "http.status_code", "value": 200}
      ],
      "logs": [],
      "process": {
        "serviceName": "user-service"
      }
    }
  ]
}
```

## OpenTelemetry Collector

For OTLP endpoints:
- Trace query: Use Jaeger API (if using Jaeger backend)
- Direct export: Use OTLP/gRPC or OTLP/HTTP

### OTLP Trace Export

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(endpoint="http://otel-collector:4317")
```
