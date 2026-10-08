---
title: Database Latency Troubleshooting
document_type: troubleshooting
version: 1
services: [postgresql, incident-service]
incident_types: [dependency_failure, high_latency]
synthetic: true
---
# Database Latency Troubleshooting

## Locate the wait

Separate connection acquisition, network establishment, lock wait, query execution, and result transfer. Compare application timers with database activity for the same interval.

## Check demand and capacity

Review active sessions, pool limits, transaction age, blocking chains, slow query fingerprints, storage latency, and CPU. Confirm whether retries or a fleet-size change increased connection demand.

## Mitigate carefully

Stop a clearly runaway batch or roll back a correlated query change. Cancel sessions only after identifying owners and transaction effects. Do not raise every pool limit; total client capacity must remain below a safe database bound.

## Verify

Confirm acquisition time, query latency, locks, errors, and application tail latency recover together. Watch backlog draining for a second saturation event.
