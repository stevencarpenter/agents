---
name: data-engineering-guidelines
description: Use when designing, building, or reviewing lakehouse tables, batch or streaming data pipelines, governance, or data for ML and retrieval. Apply only the sections relevant to the requested data work.
---

# Data Engineering Guidelines

Understand the data contract, existing platform, and access pattern before changing a pipeline. Reuse infrastructure that meets the requirements. Compare vendors when choosing a new component, not when the user has already selected a suitable platform. A narrow transform fix does not require redesigning storage, governance, or orchestration.

## Source Of Truth

- The data contract: schema, semantics, freshness/latency SLA, expected volume, ownership, and downstream consumers. Establish missing details that affect the change; a small correction does not require a separate contract document.
- The live catalog and lineage (Unity Catalog, Glue, Hive Metastore, or an Iceberg catalog): what exists, who reads it, and how it's governed.
- The platform's own behavior — read the engine docs for the exact version. Streaming and table-format semantics change between releases.

## Lakehouse Table Design

- **Table format:** use Delta Lake or Iceberg when transactional updates, concurrent writers, schema evolution, or snapshot reads require a table format. Plain Parquet can serve an immutable export or bounded batch dataset. Check engine/catalog compatibility; do not assume formats or writers are interchangeable.
- **Layering:** preserve raw inputs when replay or audit requires them. Separate cleaning and serving datasets when they have different contracts or consumers; do not create bronze, silver, and gold tables for every small pipeline. Derived layers must be reproducible from retained inputs.
- **Partitioning & clustering:** partition on low-cardinality columns that match query filters (usually a date). Do not over-partition — small partitions create the small-files problem. Prefer liquid clustering (Delta) or hidden partitioning (Iceberg) over manual partition columns where available; use Z-order/clustering for high-cardinality filter columns.
- **File sizing & compaction:** target ~128MB–1GB files. Prefer engine **auto-compaction / optimized-writes** (Delta) or Iceberg auto-compaction where available; manual `OPTIMIZE` is the fallback, not the default. Expire snapshots / `VACUUM` on a schedule — but never below your time-travel retention window, or you silently break reproducibility and CDC replay. The small-files problem is the most common lakehouse performance killer.
- **Schema evolution:** additive by default. Check the selected table format's rename/drop requirements, including column mapping where required. Never silently widen or coerce types; make breaking changes explicit and versioned.
- **Upserts & CDC:** use `MERGE` for upserts and SCD handling; ingest change feeds (Debezium, Delta CDF, Iceberg changelog) rather than full reloads. Make every merge idempotent on a stable business key.
- **Time travel:** use it for audit, reproducibility, and recovery — but it pins storage; set retention deliberately.

## Streaming & Realtime

- **Kafka:** choose the partition key for ordering and parallelism (events that must stay ordered share a key). Enforce schemas via a schema registry; evolve them with compatibility rules. Decide delivery semantics up front (at-least-once vs exactly-once) and design consumers to match.
- **Processing engine:** use the existing engine when it meets the latency and scale requirements. For stateful streaming, reason explicitly about:
  - **Event time vs processing time** — process on event time; set **watermarks** to bound state and define lateness. For every windowed/aggregated output, state the watermark-drop consequence explicitly — records later than the watermark silently vanish from the aggregate — and name the disposition (drop with quantified acceptable loss, side-output to a late-arrivals table, or periodic reconciliation).
  - **Windowing** — tumbling/sliding/session; match the window to the business question.
  - **State & checkpointing** — checkpoint to durable storage; size and TTL state so it doesn't grow unbounded; plan for state-schema migration.
  - **Exactly-once** — idempotent sinks plus checkpointed offsets; never assume exactly-once without verifying the sink supports it. State the exact idempotent write mechanism (MERGE key, or deterministic overwrite-by-partition) for **every** sink in the design — aggregate and windowed tables included, not just the primary fact table.
  - **Stateful operators** (session windows, `transformWithState`, custom state): address checkpoint/state-schema compatibility across code deployments as part of the recovery story — a state-logic change that invalidates the checkpoint is a real outage mode.
- **Declarative first:** prefer existing SQL/DataFrame operations or platform-managed incremental tables where they express the required semantics. Do not introduce a new service or framework merely to avoid a small supported `foreachBatch` operation.
- **Streaming into the lakehouse:** use checkpointed writes and idempotent upserts where required. Bound state and apply the agreed lateness policy; add batch reconciliation when tolerated loss or correctness requirements call for it.
- **Backpressure & late data:** bound input rate, monitor consumer lag, and define what happens to data that arrives after the watermark (drop, side-output, or reconcile).

## Governance

For a new pipeline or changed data boundary, identify data classification and authorized readers. Preserve existing controls during narrow edits; do not create a separate governance project when the access boundary is unchanged.

- Govern through the catalog (Unity Catalog or equivalent): least-privilege grants, lineage, and audit. Tag and isolate PII; mask or tokenize at the silver layer, not in ad-hoc queries.
- Enforce fine-grained access centrally when required, using existing catalog policies, row filters, or column masks. Use ABAC when the authorization model warrants it; simple grants can suffice for a small uniform audience.
- Use governed sharing mechanisms for cross-boundary consumption when access controls and revocation require them.
- Manage credentials through the platform's identity/secret mechanism — never inline them in code or notebooks.

## AI/ML Data Support

- **Feature stores:** keep offline (training) and online (serving) definitions in sync to avoid training/serving skew. Compute features once, serve both.
- **Point-in-time correctness:** build training sets with as-of joins so a feature value reflects only what was known at the label's timestamp. Leaking future data is the most common silent ML-data bug.
- **Reproducibility:** version training data (table snapshot / time-travel version), feature code, and the query that produced the set so a model run is reconstructable. Apply this when ML, audit, or a consumer contract requires reproducibility; hypothetical future ML use does not expand every pipeline task.
- **Vector / RAG:** version the embedding model, chunking strategy, and source snapshot; re-embed when a relevant input changes. Keep additions, updates, and deletions synchronized using the existing refresh or CDC path that meets the freshness and scale requirements.
- **MLOps handoff:** hand clean, documented, monitored datasets to the model registry/serving layer; expose freshness and schema so monitoring can detect drift. Distinguish the kinds: input **data drift**, **feature drift**, and — for RAG — **embedding-distribution drift** and **retrieval-quality** regression. Monitor each where it lives, not just at the model output.

## Data Quality & Reliability

- Validate the contract at pipeline boundaries with existing engine constraints or configured quality tooling. Assign violations an explicit disposition (drop, quarantine, or fail) based on the contract; fail on violations that prevent safe processing. Do not add a quality framework or a fabricated failure class to satisfy this rubric.
- Make every pipeline **idempotent and replayable**: re-running a window or partition must produce the same result. Key sinks on stable business keys; prefer overwrite-by-partition or MERGE over blind append.
- Define replay/backfill and recovery for persisted pipeline changes using retained inputs and deterministic reads. Update an existing runbook when available; create one when an operator needs a repeatable recovery procedure.
- Monitor freshness, row-volume anomalies, schema changes, and null-rate drift — alert on the data, not just on job success.

## Performance & Cost

- The usual lakehouse bottlenecks: small files (compact), data skew (salt or repartition hot keys), oversized shuffles (broadcast small dimensions, prune early), and full scans (partition pruning, predicate/projection pushdown).
- Right-size compute using measured workload and shuffle volume. Consider existing autoscaling or vectorized execution when it improves cost or latency; cache only reused data.
- Cost is a design constraint: cheaper to filter at bronze than to scan gold. Measure with the query plan and the platform's cost/usage views before and after changes.

## Output Contract

Deliver the requested implementation or design at its actual scope. A new production pipeline needs its contract, validation, access controls, idempotency, and recovery explained; a narrow change needs the affected behavior and proof. For a review, name the failure mode, show evidence, and give the smallest correction that preserves the contract.
