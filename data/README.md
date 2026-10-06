# Telemetry datasets

Phase 4 writes reproducible Parquet datasets to `data/features/<dataset-id>/`.
Those generated directories are ignored. Only `data/features/README.md` is
tracked so the output contract and deletion behavior remain visible.

Phase 1 writes locally captured OpenTelemetry data to `data/raw/<run-id>/`.
Each successful run contains separate `metrics.jsonl`, `logs.jsonl`, and
`traces.jsonl` files plus a ground-truth `manifest.json`.

`data/raw/` is intentionally ignored except for its `.gitkeep`. Raw captures can
be large and may contain environment-specific operational data; do not commit
them. `data/samples/` is reserved for a future deliberately curated, very small,
and reviewed sample—not arbitrary capture output.
