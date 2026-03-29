# Trace Fetching Examples

## Example 1: Fetch Single Trace

**Input:**
```bash
python scripts/fetch_trace.py \
  --endpoint http://jaeger:16686 \
  --trace-id 4f8d9c2e8a7b3f1e
```

**Output (timeline format):**
```
Trace: 4f8d9c2e8a7b3f1e
Total Spans: 12
Duration: 245ms

Timeline:
[0ms    ] ├─ GET /api/order (order-service)
[5ms    ] │  ├─ SELECT * FROM orders (db-service) - 15ms
[25ms   ] │  ├─ POST /payment (payment-service)
[30ms   ] │  │  ├─ validate-card (payment-service) - 45ms
[80ms   ] │  │  └─ process-payment (payment-service) - 120ms
[205ms  ] │  └─ UPDATE inventory (inventory-service) - 35ms
[245ms  ] └─ [END]
```

## Example 2: Search Error Traces

**Input:**
```bash
python scripts/fetch_trace.py \
  --endpoint http://jaeger:16686 \
  --service payment-service \
  --tags '{"error": "true"}' \
  --start 2024-01-01T00:00:00 \
  --end 2024-01-01T23:59:59 \
  --limit 10
```

**Output:**
```json
{
  "traces": [
    {
      "traceID": "a1b2c3d4e5f6",
      "spans": [
        {
          "operationName": "POST /payment",
          "tags": [
            {"key": "error", "value": true},
            {"key": "error.message", "value": "Card declined"}
          ]
        }
      ]
    }
  ]
}
```

## Example 3: Analyze Latency

**Input:**
```bash
python scripts/fetch_trace.py \
  --endpoint http://jaeger:16686 \
  --service api-gateway \
  --minDuration 500ms \
  --limit 20 \
  --format flamegraph
```

**Output:**
```
api-gateway;GET /api/users 850ms
api-gateway;GET /api/users;user-service;getUser 650ms
api-gateway;GET /api/users;user-service;getUser;db-query 400ms
api-gateway;GET /api/users;cache-check 150ms
```

## Example 4: Export for Analysis

**Input:**
```bash
python scripts/fetch_trace.py \
  --endpoint http://jaeger:16686 \
  --service order-service \
  --start 2024-01-01T00:00:00 \
  --end 2024-01-07T23:59:59 \
  --output weekly-traces.json
```

**Then analyze with jq:**
```bash
# Find slowest traces
jq '.traces | sort_by(.duration) | reverse | .[0:5]' weekly-traces.json

# Count errors by service
jq '.traces[].spans[] | select(.tags[]?.value == true) | .process.serviceName' weekly-traces.json | sort | uniq -c
```
