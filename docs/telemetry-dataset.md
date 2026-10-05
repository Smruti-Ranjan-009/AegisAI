# Telemetry Dataset Laboratory

## Purpose and scope

Phase 1 uses the official OpenTelemetry Demo because it provides realistic, polyglot distributed-service traffic and deterministic feature-flag faults. The lab captures raw telemetry and experiment ground truth for later phases. It does not aggregate features, train models, publish events to Kafka, or provide a production observability backend.

The upstream source is not vendored. `python scripts\telemetry_lab.py setup` clones it to `.runtime/opentelemetry-demo`, checks out tag `3.1.0`, and verifies commit `dedc0178918e260823323b8d95005a8cb924b007`. The clone and generated data remain ignored by Git.

## Offline data path

```text
OpenTelemetry Demo 3.1.0 + built-in Locust traffic
                        |
                        | OTLP metrics / logs / traces
                        v
             OpenTelemetry Collector
                 |         |         |
                 v         v         v
          metrics.jsonl logs.jsonl traces.jsonl
                 \         |         /
                  +---- manifest.json
                              |
                              v
                    Raw labeled dataset
```

Only the upstream core `compose.yaml` is used with `infrastructure/telemetry-lab/compose.capture.yml`. The full, observability, and extras Compose files are not used. Upstream PostgreSQL and Valkey are application-internal demo dependencies; they are not AegisAI's planned production storage. The project name `aegis-telemetry-lab`, frontend port `18080`, and Envoy admin port `19000` isolate the lab from the Phase 0 stack.

The AegisAI Collector extras file adds three file exporters while retaining upstream receivers, processors, the debug exporter, and the span-metrics connector. Each exporter writes OTLP JSON, one batch per line, to a host-mounted run directory. Metrics describe service/runtime/resource measurements, logs describe emitted application and infrastructure records, and traces describe distributed request spans.

## Experiment lifecycle

Each run performs the following guarded sequence:

1. Verify Docker, Compose v2, the pinned checkout, and scenario definitions.
2. Reset all managed flags to healthy variants and verify them through flagd OFREP.
3. Warm up and confirm the frontend plus captured traffic/service identity.
4. Create a collision-resistant UTC run ID and fresh directory.
5. Apply at most one fault and verify the live flag value.
6. Recreate the Collector with that run's host directory, capture, flush, and stop it.
7. Restore and verify every managed flag in guaranteed cleanup logic.
8. Restore an idle Collector, write the manifest atomically, and validate the completed run.

Interrupted or invalid runs are never reported as successful. The upstream checkout is never edited: the lab mounts a runtime copy of `demo.flagd.json` and restores healthy variants even when capture fails.

## Scenarios and labels

All names and variants below are verified against the pinned `src/flagd/demo.flagd.json`.

| Scenario | Ground-truth label | Upstream flag | Fault variant | Healthy variant | Expected services |
| --- | --- | --- | --- | --- | --- |
| `normal` | `normal` | none | none | all managed flags healthy | none required |
| `cpu_saturation` | `cpu_saturation` | `adHighCpu` | `on` | `off` | `ad` |
| `memory_leak` | `memory_leak` | `emailMemoryLeak` | `100x` | `off` | `email` |
| `service_failure` | `service_failure` | `paymentFailure` | `100%` | `off` | `payment` |
| `dependency_failure` | `dependency_failure` | `paymentUnreachable` | `on` | `off` | `checkout`, `payment` |
| `high_latency` | `high_latency` | `imageSlowLoad` | `5sec` | `off` | `frontend`, `image-provider` |

`run-all` executes scenarios sequentially, never concurrently. Phase 1 integration validation exercises normal and CPU saturation; the other mappings are statically verified and available for developer runs.

## Dataset layout and manifest

```text
data/raw/20261005T153012Z-cpu-saturation-a1b2c3/
|-- metrics.jsonl
|-- logs.jsonl
|-- traces.jsonl
`-- manifest.json
```

The schema-version-1 manifest contains the unique run ID, scenario, ground-truth label, UTC start/end timestamps, requested duration, pinned demo version and commit, fault name/variant/baseline/restoration status, expected affected services, pre-capture traffic services, and signal filenames. It contains no ML features.

```json
{
  "schema_version": 1,
  "run_id": "20261005T153012Z-cpu-saturation-a1b2c3",
  "scenario": "cpu_saturation",
  "label": "cpu_saturation",
  "started_at_utc": "2026-10-05T15:30:12Z",
  "ended_at_utc": "2026-10-05T15:31:12Z",
  "duration_seconds": 60,
  "otel_demo_version": "3.1.0",
  "upstream_git_commit": "dedc0178918e260823323b8d95005a8cb924b007",
  "feature_flag": {
    "name": "adHighCpu",
    "variant": "on",
    "baseline_variant": "off",
    "restored": true
  },
  "expected_affected_services": ["ad"],
  "traffic_services_observed_before_capture": ["frontend", "load-generator"],
  "signals": {
    "metrics": "metrics.jsonl",
    "logs": "logs.jsonl",
    "traces": "traces.jsonl"
  }
}
```

Validation requires all four files, non-empty signal files, valid JSON on every non-empty line, the matching OTLP root (`resourceMetrics`, `resourceLogs`, or `resourceSpans`), at least one `service.name`, all required manifest fields, safe in-root paths, and expected affected service identities for fault runs.

## Operating the lab

Prerequisites are Git, Python 3.12, Docker Desktop with a reachable daemon, and Docker Compose v2. The CLI fails with an actionable message and never starts Docker Desktop automatically.

```powershell
conda activate aegis
python scripts\telemetry_lab.py setup
python scripts\telemetry_lab.py scenarios
python scripts\telemetry_lab.py start
python scripts\telemetry_lab.py status

python scripts\telemetry_lab.py run `
  --scenario normal `
  --warmup 20 `
  --duration 60 `
  --fault-propagation 10 `
  --flush-delay 5

python scripts\telemetry_lab.py run `
  --scenario cpu_saturation `
  --warmup 20 `
  --duration 60 `
  --fault-propagation 10 `
  --flush-delay 5

python scripts\telemetry_lab.py validate --run <run-id>
python scripts\telemetry_lab.py stop
```

Setup downloads a source clone and multiple container images, so several gigabytes of free disk should be available. Raw JSONL grows with traffic rate and duration; short runs can already produce megabytes. Monitor `data/raw` and Docker disk usage locally. No capture is deleted automatically.

Cleanup is explicit, refuses to run while the lab is active, stays inside the repository, preserves `data/raw/.gitkeep`, and requires typed confirmation unless `--yes` is supplied:

```powershell
python scripts\telemetry_lab.py stop
python scripts\telemetry_lab.py clean --captures
python scripts\telemetry_lab.py clean --runtime
# or, after reviewing the targets:
python scripts\telemetry_lab.py clean --all --yes
```

## Limitations

- This is an offline development data path, not the final production ingestion architecture.
- The official core demo still starts its internal PostgreSQL and Valkey dependencies.
- Upstream `compose.yaml` assigns fixed container names; the dedicated project/network avoids AegisAI conflicts, but a second OpenTelemetry Demo stack with the same names cannot run concurrently.
- Collector host/process receivers may occasionally log transient scrape races as short-lived container processes exit; completed captures still undergo strict file validation.
- Ground truth describes the injected condition and expected services, not proof that every request exhibited the fault.
- JSONL captures may contain environment-specific operational data and must not be committed.
- Kafka streaming begins in Phase 2. Feature engineering and ML remain later phases.
