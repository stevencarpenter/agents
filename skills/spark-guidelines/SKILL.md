---
name: spark-guidelines
description: Use when designing, building, or reviewing Apache Spark 4 data pipelines — batch and streaming DataFrame transforms, lakehouse sinks (Delta/Iceberg), Spark Connect, Structured Streaming (watermarks, checkpoints, transformWithState, state data source), partitioning/AQE/shuffle optimization, and idempotent MERGE/CDC patterns. Reach for this whenever the user mentions Spark, PySpark, Structured Streaming, lakehouse ETL, or distributed dataframe pipelines even if they do not name Spark 4 explicitly.
---

# Spark Guidelines

Shared Spark 4 rubric for agents building expert-level data pipelines. Vendor-general — applies to open-source Spark, Databricks Runtime 16.x+, EMR, or any Spark 4 cluster. Pair with `spark-scala-guidelines` or `spark-pyspark-guidelines` for language-specific idioms. For medallion layering, catalog governance, and cross-engine lakehouse design, also apply `data-engineering-guidelines`.

## Source Of Truth

- Apache Spark 4.x docs: https://spark.apache.org/docs/latest/
- Structured Streaming guide (especially `transformWithState`): https://spark.apache.org/docs/latest/streaming/
- The cluster's exact Spark/Delta/Iceberg versions — semantics change between releases
- The live catalog and existing table formats in the repo — match what's there

## Spark 4 Baseline

- **Assume Spark 4** unless the repo pins an older version. Key 4.x capabilities to prefer over legacy APIs:
  - **`transformWithState`** (Scala/Java/Python) replaces `mapGroupsWithState`, `flatMapGroupsWithState`, and `applyInPandasWithState` for arbitrary stateful streaming
  - **Composite state types** — `ValueState`, `ListState`, `MapState` with TTL, timers, initial state, and Avro-backed schema evolution
  - **State Store Data Source** — read streaming operator state as a DataFrame for debugging (`stateVarName`, flattened vs non-flattened)
  - **Spark Connect** — client-server mode with high feature parity; toggle via `spark.api.mode` during migration
- **Declarative first.** Express transforms as DataFrame/SQL operations. Reach for custom stateful processors or UDFs only when the declarative layer cannot express the logic.

## Pipeline Design

- **Data contract before code.** Pin schema, semantics, freshness/latency SLA, volume, partitioning strategy, and sink idempotency key before writing transforms.
- **Medallion, catalog, and lakehouse table design:** apply `data-engineering-guidelines`.
- **MERGE tie-breaks.** When CDC can deliver equal `event_timestamp` values for the same key, define a secondary ordering column (usually `ingest_timestamp` or a monotonic sequence) in both dedup and `whenMatchedUpdate` conditions — otherwise replays are nondeterministic.
- **foreachBatch idempotency.** Streaming micro-batches may be reprocessed at-least-once. Every `foreachBatch` body must be safe to run twice on the same batch (idempotent MERGE, overwrite-by-partition, or deterministic upsert key).

## DataFrame Transforms

- **Column expressions over UDFs.** Catalyst can optimize SQL/Column API; UDFs (especially Python) break vectorization and predicate pushdown. UDFs are the escape hatch, not the default.
- **Push filters and projections early.** Select only needed columns; filter at the earliest layer that has the predicate column — cheaper at bronze than at gold.
- **Join discipline:**
  - Broadcast small dimension tables (`broadcast` hint or `spark.sql.autoBroadcastJoinThreshold`)
  - Repartition or salt before join when key skew is known
  - Prefer `left_anti` / `left_semi` over subtracting full DataFrames
- **Aggregation discipline:** pre-aggregate where possible; use window functions for ranking and running metrics instead of self-joins; watch for exploding `groupBy` cardinality.
- **Deduplication:** `dropDuplicates` on business keys at silver; for streaming, use watermark + `dropDuplicatesWithinWatermark` or stateful dedup via `transformWithState`.

## Partitioning, Files & Table Formats

Apply `data-engineering-guidelines` for partitioning, file sizing, compaction, and Delta/Iceberg table design. Spark-specific: verify partition pruning and broadcast-join choices in explain plans.

## Structured Streaming

Apply `data-engineering-guidelines` for event time, watermarks, checkpointing, delivery semantics, and streaming-into-lakehouse patterns.
- **Driver OOM in streaming:** suspect `console`/`memory` sinks, `collect`, and Update-mode emissions with growing payloads before blaming executor state store size — these materialize on the driver.
- **`transformWithState` for custom state:**
  - Define logic in a `StatefulProcessor` (object-oriented lifecycle: `init`, `handleInputRows`, `close`)
  - Use composite state types instead of read-modify-write on a single blob
  - Set TTL and timers explicitly; enable Avro encoding (`spark.sql.streaming.stateStore.encodingFormat=avro`) when state schema must evolve
  - Debug via the State Store Data Source rather than println/logging state
- **Operator migration:** switching legacy stateful APIs (`flatMapGroupsWithState`, `applyInPandasWithState`) to `transformWithState` / `transformWithStateInPandas` requires a **new checkpoint location** (or documented state-store migration) — the arbitrary-state v2 store cannot read legacy checkpoints; never silently reuse the old path; record in migration notes
- **Declarative streaming tables** (Lakeflow / Spark Declarative Pipelines) when the platform supports them — prefer over hand-rolled `foreachBatch` for standard incremental refresh.

## Spark Connect

- Use Connect when the workload is remote-driver, polyglot client, or notebook-to-cluster separation.
- Keep session configuration and catalog access consistent between Connect and Classic during migration.
- Test both paths if the repo supports `spark.api.mode` toggling.

## Performance & Cost

- **Explain before and after.** `df.explain("cost")` or the Spark UI — verify partition pruning, broadcast joins, and no unexpected cartesian products.
- **AQE** (Adaptive Query Execution): leave enabled unless profiling shows a regression; watch for skew join handling.
- Common killers: small files, data skew, oversized shuffles, Python UDFs on hot paths, `collect`/`toPandas` on large datasets, caching without reuse.
- Right-size executors to shuffle volume, not wall-clock impatience. For lakehouse cost discipline, apply `data-engineering-guidelines`.

## Testing & Verification

- Unit-test transform logic with small local sessions (`local[*]` with reduced fixtures) or extracted pure functions where the logic permits.
- Integration-test writes against a temp catalog/path with overwrite cleanup.
- For streaming: use `memory` sinks or `availableNow` triggers in tests; verify checkpoint recovery separately.
- Record exact proof commands: `spark-submit`, `sbt test`, `pytest`, or the repo's pipeline runner.

## Output Contract

For a pipeline: data contract and SLAs, design (sources → transforms → sinks, layer by layer), code, data-quality checks, idempotency/backfill/recovery story, and cost/performance notes (with explain output when relevant).

For a review: name the failure mode (skew, small files, unbounded state, non-idempotent sink, Python UDF on hot path, missing watermark), show evidence (plan, code, metrics), and give the corrected idiomatic form.
