---
name: data-engineering-guidelines
description: Use when designing, building, or reviewing data-engineering work — lakehouse table design (Delta/Iceberg, medallion, partitioning, compaction, schema evolution, MERGE/CDC), realtime and streaming pipelines (Kafka, Spark Structured Streaming, Flink, watermarks, exactly-once), data governance, AI/ML data support (feature stores, vector/RAG), and data quality, reliability, and cost.
---

# Data Engineering Guidelines

Shared rubric for data-engineering agents working on lakehouse, realtime/streaming, and AI/ML data systems. Vendor-general — applies to Delta Lake or Apache Iceberg, Databricks or open-source Spark/Flink/Kafka. Understand the data contract and the access pattern before you write a pipeline. When you recommend a single-vendor component (catalog, feature store, orchestration), name at least one viable alternative and say why the pick wins — existing infra, team skillset, cost — never default silently to one vendor's stack.

## Source Of Truth

- The **data contract**: schema, semantics, freshness/latency SLA, expected volume and growth, ownership, and downstream consumers. If it isn't written down, write it down first.
- The live catalog and lineage (Unity Catalog, Glue, Hive Metastore, or an Iceberg catalog): what exists, who reads it, and how it's governed.
- The platform's own behavior — read the engine docs for the exact version. Streaming and table-format semantics change between releases.

## Lakehouse Table Design

- **Table format:** Delta Lake or Apache Iceberg, not bare Parquet — you need ACID, schema evolution, and time travel. In 2026 the formats increasingly interoperate (Delta UniForm exposes Iceberg metadata; engines read both through the **Iceberg REST catalog** spec), so decide the **catalog / REST-catalog** story first — the on-disk format is becoming a swappable detail. Still pick one primary format per platform and be consistent rather than mixing writers.
- **Medallion layering:** bronze (raw, append-only, immutable landing) → silver (cleaned, conformed, deduplicated, typed) → gold (business-level aggregates and serving tables). Each layer is reproducible from the one below.
- **Partitioning & clustering:** partition on low-cardinality columns that match query filters (usually a date). Do not over-partition — small partitions create the small-files problem. Prefer liquid clustering (Delta) or hidden partitioning (Iceberg) over manual partition columns where available; use Z-order/clustering for high-cardinality filter columns.
- **File sizing & compaction:** target ~128MB–1GB files. Prefer engine **auto-compaction / optimized-writes** (Delta) or Iceberg auto-compaction where available; manual `OPTIMIZE` is the fallback, not the default. Expire snapshots / `VACUUM` on a schedule — but never below your time-travel retention window, or you silently break reproducibility and CDC replay. The small-files problem is the most common lakehouse performance killer.
- **Schema evolution:** additive by default. Enable column mapping before renames/drops. Never silently widen or coerce types — make breaking changes explicit and versioned.
- **Upserts & CDC:** use `MERGE` for upserts and SCD handling; ingest change feeds (Debezium, Delta CDF, Iceberg changelog) rather than full reloads. Make every merge idempotent on a stable business key.
- **Time travel:** use it for audit, reproducibility, and recovery — but it pins storage; set retention deliberately.

## Streaming & Realtime

- **Kafka:** choose the partition key for ordering and parallelism (events that must stay ordered share a key). Enforce schemas via a schema registry; evolve them with compatibility rules. Decide delivery semantics up front (at-least-once vs exactly-once) and design consumers to match.
- **Processing engine:** Spark Structured Streaming or Flink. Reason explicitly about:
  - **Event time vs processing time** — process on event time; set **watermarks** to bound state and define lateness. For every windowed/aggregated output, state the watermark-drop consequence explicitly — records later than the watermark silently vanish from the aggregate — and name the disposition (drop with quantified acceptable loss, side-output to a late-arrivals table, or periodic reconciliation).
  - **Windowing** — tumbling/sliding/session; match the window to the business question.
  - **State & checkpointing** — checkpoint to durable storage; size and TTL state so it doesn't grow unbounded; plan for state-schema migration.
  - **Exactly-once** — idempotent sinks plus checkpointed offsets; never assume exactly-once without verifying the sink supports it. State the exact idempotent write mechanism (MERGE key, or deterministic overwrite-by-partition) for **every** sink in the design — aggregate and windowed tables included, not just the primary fact table.
  - **Stateful operators** (session windows, `transformWithState`, custom state): address checkpoint/state-schema compatibility across code deployments as part of the recovery story — a state-logic change that invalidates the checkpoint is a real outage mode.
- **Declarative first:** reach for **declarative streaming tables / materialized views** (Lakeflow / Spark Declarative Pipelines, or Flink + Paimon) as the default — they manage checkpoints, incremental refresh, and dependencies for you. Hand-rolled `foreachBatch` is the escape hatch for logic the declarative layer can't express, not the starting point.
- **Streaming into the lakehouse:** stream into Delta/Iceberg with checkpointed micro-batches; use `foreachBatch` for upserts/MERGE into silver. Handle late data with watermarks plus a periodic batch reconciliation rather than unbounded state.
- **Backpressure & late data:** bound input rate, monitor consumer lag, and define what happens to data that arrives after the watermark (drop, side-output, or reconcile).

## Governance

Governance is a non-skippable part of every pipeline design — include a PII/classification/access-control disposition even when the prompt doesn't ask for it. A design that never mentions who may read the data, or where PII is masked, is incomplete.

- Govern through the catalog (Unity Catalog or equivalent): least-privilege grants, lineage, and audit. Tag and isolate PII; mask or tokenize at the silver layer, not in ad-hoc queries.
- Enforce fine-grained access in the catalog, not the query: **row-level filters and column-level masking policies**, and **attribute-based access control (ABAC)** driven by catalog tags rather than per-table grant sprawl.
- Publish governed **data products / shares** (Delta Sharing, Iceberg) for cross-team and cross-org consumption instead of handing out raw table grants.
- Manage credentials through the platform's identity/secret mechanism — never inline them in code or notebooks.

## AI/ML Data Support

- **Feature stores:** keep offline (training) and online (serving) definitions in sync to avoid training/serving skew. Compute features once, serve both.
- **Point-in-time correctness:** build training sets with as-of joins so a feature value reflects only what was known at the label's timestamp. Leaking future data is the most common silent ML-data bug.
- **Reproducibility:** version training data (table snapshot / time-travel version), feature code, and the query that produced the set. A model run should be reconstructable. Even when a task isn't ML-labeled, if the pipeline could feed training or features, say how a consumer pins a reproducible snapshot (time-travel version/timestamp) of the table.
- **Vector / RAG:** treat embeddings as a derived gold dataset — version the embedding model, chunking strategy, and source snapshot; plan for re-embedding when any of them change. Keep the vector index in sync with source updates via the same CDC path.
- **MLOps handoff:** hand clean, documented, monitored datasets to the model registry/serving layer; expose freshness and schema so monitoring can detect drift. Distinguish the kinds: input **data drift**, **feature drift**, and — for RAG — **embedding-distribution drift** and **retrieval-quality** regression. Monitor each where it lives, not just at the model output.

## Data Quality & Reliability

- Enforce expectations at pipeline boundaries (DLT/Lakeflow expectations, Great Expectations, or dbt tests): not-null, uniqueness, referential integrity, range, and freshness. Assign every check one of the three dispositions explicitly — **drop**, **quarantine**, or **fail the run** — and make sure at least one violation class is severe enough to fail fast (e.g. an upstream schema-contract break); a design that only ever drops or quarantines has no brakes.
- Make every pipeline **idempotent and replayable**: re-running a window or partition must produce the same result. Key sinks on stable business keys; prefer overwrite-by-partition or MERGE over blind append.
- Design backfill and recovery from the start: partition-level reprocessing, deterministic reads from bronze, and a documented "how to replay the last N days" runbook.
- Monitor freshness, row-volume anomalies, schema changes, and null-rate drift — alert on the data, not just on job success.

## Performance & Cost

- The usual lakehouse bottlenecks: small files (compact), data skew (salt or repartition hot keys), oversized shuffles (broadcast small dimensions, prune early), and full scans (partition pruning, predicate/projection pushdown).
- Right-size compute: prefer serverless/autoscaling where it fits; enable Photon/vectorized execution; cache only what is reused. Match cluster size to shuffle volume, not to wall-clock impatience.
- Cost is a design constraint: cheaper to filter at bronze than to scan gold. Measure with the query plan and the platform's cost/usage views before and after changes.

## Output Contract

For a pipeline, deliver: the data contract and SLAs, the design (sources → transforms → sinks, layer by layer), the code, the data-quality checks with their dispositions, the governance/PII disposition, the idempotency/backfill/recovery story, and cost notes. For a review, name the failure mode (skew, small files, unbounded state, training/serving skew, non-idempotent sink), show the evidence, and give the corrected form.
