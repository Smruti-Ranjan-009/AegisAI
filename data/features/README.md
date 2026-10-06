# Generated feature datasets

The Phase 4 CLI writes each deterministic dataset to a subdirectory containing:

```text
service_windows.parquet
metric_windows.parquet
manifest.json
quality.json
```

Dataset subdirectories are generated, potentially large, and intentionally
Git-ignored. They can be rebuilt from their source run IDs and configuration.
Deleting this directory does not modify the read-only captures in `data/raw/`.
