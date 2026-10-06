# Phase 4 telemetry feature inventory

This compact inventory was produced from the two existing read-only Phase 1
captures on 2026-10-06. The complete machine-readable inventory remains available
through `python -m aegis_features.cli inspect --run <run-id>`; it is not copied
into a giant generated document.

## Sources

| Run | Scenario | OTLP records (M/L/T) | Observations (M/L/T) | Services | Metric identities |
|---|---|---:|---:|---:|---:|
| `20261005T095734Z-normal-6cc5c1` | normal | 33 / 118 / 91 | 3,757 / 417 / 909 | 18 | 265 |
| `20261005T095842Z-cpu-saturation-cd027d` | cpu_saturation | 32 / 117 / 82 | 3,414 / 340 / 454 | 18 | 265 |

The union contains 265 distinct `(metric_name, unit, metric_type)` identities:
189 Sum, 54 Gauge, and 22 Histogram. No ExponentialHistogram or Summary appeared
in these captures, though v1 supports both and tests them.

Observed application and request metric names include:

```text
demo.ad.requests
demo.cart.add_item.latency
demo.cart.get_cart.latency
demo.exchange.conversions_counter
demo.notification.confirmations
demo.payment.transactions
demo.recommendation.requests
demo.shipping.items_shipped
demo_ad_served_total
db.client.operation.duration
http.client.request.duration
http.server.request.duration
rpc.client.call.duration
rpc.client.duration
rpc.client.request.size
rpc.client.response.size
rpc.server.call.duration
rpc.server.duration
rpc.server.request.size
rpc.server.response.size
quotes
```

The remaining inventory spans runtime and infrastructure families including
`aspnetcore.*`, `container.*`, `cpython.*`, `db.sql.*`, `dotnet.*`,
`feature_flag.*`, `go.*`, `http.*`, `jvm.*`, `kafka.*`, `nodejs.*`, `process.*`,
`redis.*`, `system.*`, and `v8js.*`. Units include unitless `1`, bytes, seconds,
milliseconds, nanoseconds, microseconds, percentages, and semantic counts. Names
and units remain separate in the long-form metric table.

Metric-emitting resource services observed were `ad`, `cart`, `checkout`,
`currency`, `email`, `frontend`, `load-generator`, `payment`, `product-catalog`,
`quote`, `recommendation`, `shipping`, and `__unknown__`.

## Logs and spans

Combined OTLP log severity distribution:

| Severity | Count |
|---|---:|
| INFO | 655 |
| WARN | 6 |
| ERROR | 1 |
| UNSPECIFIED | 95 |

Combined span kind distribution:

| Kind | Count |
|---|---:|
| CLIENT | 508 |
| INTERNAL | 259 |
| SERVER | 596 |

## Quality observation

The two-run build retained 5,229 `__unknown__` observations. Inspection shows
these are predominantly host, container, system, and Redis receiver metrics whose
OTLP resources do not carry `service.name`; they were reported rather than
silently discarded or assigned to an application service.

## Lightweight sanity comparison

Means below describe all service-window rows in each run. Services and window
coverage differ, so this is a plausibility check—not evidence of causal effect or
model separability.

| Feature | normal mean | cpu_saturation mean | observed combined range |
|---|---:|---:|---:|
| `log_error_rate` | 0.000000 | 0.000487 | 0–0.017544 |
| `log_warn_rate` | 0.001493 | 0.002802 | 0–0.083333 |
| `span_error_rate` | 0.000398 | 0.002222 | 0–0.080000 |
| `span_duration_ms_p95` | 62.219803 | 205.289656 | 0–3958.183679 |
| `telemetry_observation_count` | 163.967742 | 116.888889 | 1–2093 |

All generated rates were within `[0, 1]`, durations were non-negative, counts
were non-negative, and every window end followed its start. Source-manifest
labels matched all output rows.

The inventory is descriptive only. It does not select features, train a model,
or demonstrate that either scenario is separable.
