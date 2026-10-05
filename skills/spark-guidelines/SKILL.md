---
name: spark-guidelines
description: Use when designing, building, or reviewing Apache Spark batch or Structured Streaming pipelines, Spark Connect, or Spark execution plans. Confirm the deployed Spark version before choosing APIs; generic lakehouse work alone does not require Spark.
---

# Spark Guidelines

Shared rubric for Spark pipelines. Confirm repository and cluster versions before choosing Spark 4 APIs; use capabilities supported by the deployed runtime that address a requirement and do not migrate a working operator solely because a newer API exists. Pair with `spark-scala-guidelines` or `spark-pyspark-guidelines` for language idioms. Apply `data-engineering-guidelines` for partitioning, file sizing, compaction, Delta/Iceberg table design, governance, and recovery.

## Source Of Truth

- Apache Spark 4.x docs: https://spark.apache.org/docs/latest/
- Structured Streaming guide (especially `transformWithState`): https://spark.apache.org/docs/latest/streaming/
- The cluster's exact Spark/Delta/Iceberg versions — semantics change between releases
- The live catalog and existing table formats in the repo — match what's there

## Pipeline Design

- **Data contract before code.** Establish the schema, semantics, and sink behavior affected by the change. A new pipeline also needs latency, volume, and recovery requirements; a small transform edit does not require a new architecture document.
- **Medallion, catalog, and lakehouse table design:** apply `data-engineering-guidelines`.
- **MERGE tie-breaks.** When CDC can deliver equal `event_timestamp` values for the same key, define a secondary ordering column (usually `ingest_timestamp` or a monotonic sequence) in both dedup and `whenMatchedUpdate` conditions — otherwise replays are nondeterministic.
- **foreachBatch idempotency.** Streaming micro-batches may be reprocessed at-least-once. Every `foreachBatch` body must be safe to run twice on the same batch (idempotent MERGE, overwrite-by-partition, or deterministic upsert key).

## DataFrame Transforms

- **Declarative first.** Express transforms as DataFrame/SQL operations; use custom stateful processors or UDFs only when the declarative layer cannot express the logic. Catalyst can optimize SQL/Column API; UDFs (especially Python) break vectorization and predicate pushdown.
- **Push filters and projections early.** Select only needed columns; filter at the earliest layer that has the predicate column — cheaper at bronze than at gold.
- **Join discipline:**
  - Broadcast small dimension tables (`broadcast` hint or `spark.sql.autoBroadcastJoinThreshold`)
  - Repartition or salt before join when key skew is known
  - Prefer `left_anti` / `left_semi` over subtracting full DataFrames
- **Aggregation discipline:** pre-aggregate where possible; use window functions for ranking and running metrics instead of self-joins; watch for exploding `groupBy` cardinality.
- **Deduplication:** use `dropDuplicates` when duplicate rows are interchangeable. For latest-record CDC, use deterministic ordering and the MERGE tie-break policy. In streaming, use supported watermark-aware dedup before custom state.

## Structured Streaming

Apply `data-engineering-guidelines` for event time, watermarks, checkpointing, delivery semantics, and streaming-into-lakehouse patterns.
- **Driver OOM in streaming:** suspect `console`/`memory` sinks, `collect`, and Update-mode emissions with growing payloads before blaming executor state store size — these materialize on the driver.
- **`transformWithState` (Scala/Java/Python) for custom state that built-in operators cannot express:**
  - Define logic in a `StatefulProcessor` (object-oriented lifecycle: `init`, `handleInputRows`, `close`)
  - Use `ValueState`, `ListState`, and `MapState` instead of read-modify-write on a single blob; use initial-state support when needed
  - Set TTL and timers explicitly; enable Avro encoding (`spark.sql.streaming.stateStore.encodingFormat=avro`) when state schema must evolve
  - Debug by reading operator state as a DataFrame via the State Store Data Source (`stateVarName`, flattened vs non-flattened), rather than println/logging state
- **Operator migration:** switching legacy stateful APIs (`mapGroupsWithState`, `flatMapGroupsWithState`, `applyInPandasWithState`) to `transformWithState` / `transformWithStateInPandas` requires a **new checkpoint location** (or documented state-store migration). The arbitrary-state v2 store cannot read legacy checkpoints; never silently reuse the old path; record in migration notes
- **Declarative streaming tables** can simplify standard incremental refresh on a platform that already supports them; do not introduce a platform migration for a narrow pipeline change.

## Spark Connect

- Use Connect's client-server mode with high feature parity when the workload is remote-driver, polyglot client, or notebook-to-cluster separation.
- Toggle via `spark.api.mode` during migration; keep session configuration and catalog access consistent between Connect and Classic.
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

For implementation, deliver the affected code and proof. Include contract, quality, idempotency, recovery, and performance details that the change affects; a new production pipeline warrants the full design.

For a review: name the failure mode (skew, small files, unbounded state, non-idempotent sink, Python UDF on hot path, missing watermark), show evidence (plan, code, metrics), and give the corrected idiomatic form.
