---
name: spark-scala-guidelines
description: Use when writing or reviewing idiomatic Scala Spark 4 code — Dataset API and Encoders, case-class schemas, transformWithState StatefulProcessor, typed aggregations, Catalyst-friendly Column transforms, and sbt/Maven Spark module layout. Trigger whenever Scala Spark, Spark SQL in Scala, or Dataset-based pipelines are in scope even if the user only says "Scala ETL on Spark."
---

# Spark Scala Guidelines

Language-specific Spark 4 rubric for Scala agents. Always apply `spark-guidelines` first for engine-level pipeline design; use this skill for Scala idioms. General Scala style still applies — immutability-first, exhaustive matching over sealed ADTs, no `null` or `Await.result` in domain code; for substantial non-Spark Scala modules, defer to the scala-implementer or scala-reviewer agents, which carry the full `scala-guidelines` rubric.

## Source Of Truth

- Spark Scala API docs: https://spark.apache.org/docs/latest/api/scala/
- Structured Streaming `transformWithState` Scala examples in the official guide
- The repo's `build.sbt`/`build.mill` — Spark version, Scala version (2.12 vs 2.13 vs 3.x), and shading rules

## API Choice

- **DataFrame by default** for ETL breadth and SQL interoperability. Reach for **Dataset[T]** when:
  - The element type is stable and encoded with a case class + `Encoders.product`
  - You need compile-time type safety on map/filter operations that would be error-prone as string column names
  - You are building a reusable library API consumed by other Scala modules
- Do not use Dataset for pipelines that are primarily SQL or PySpark-portable — the encoding overhead and version coupling rarely pay off.
- **Never use RDD** in new Spark 4 pipeline code unless interfacing with legacy libraries that have no DataFrame equivalent.

## Idiomatic Transforms

- Express transforms as **Column expressions** and `select`/`withColumn` chains. Reserve Scala UDFs for logic that cannot be expressed in Catalyst (complex parsing, external library calls).
- When a UDF is necessary, define it as a **named function** with an explicit return type and register with `udf`. Keep UDFs pure and side-effect free.
- Prefer **`transform`** on DataFrame for reusable pipeline steps — a function `DataFrame => DataFrame` composes cleanly and reads as a pipeline stage.
- Use **`na.fill` / `na.drop`** and built-in functions (`regexp_extract`, `from_json`, `explode`, `aggregate`) before reaching for UDFs.

## Schemas & Types

- Model row types as **case classes** with `Encoders.product[MyRow]` for Dataset paths.
- Define nested schemas with case classes or `StructType` in a shared `schema` object — do not scatter string column names.
- For JSON/Avro/Protobuf ingestion, use **`from_json` / `from_avro`** with an explicit schema rather than inferring on production paths.
- Enable **schema evolution** at the table format layer (Delta/Iceberg); in code, handle additive columns with defaults, not silent casts.

## Structured Streaming in Scala

- Use **`transformWithState`** with a class extending `StatefulProcessor`:
  - `init` for state handle setup (`getValueState`, `getListState`, `getMapState`)
  - `handleInputRows` for per-batch logic
  - `close` for cleanup
- Set **`timeMode`** explicitly — `TimeMode.None()`, `TimeMode.ProcessingTime()`, or `TimeMode.EventTime()` — to match the business requirement.
- Register **event-time timers** and **TTL** in `init` rather than manual expiry logic in `handleInputRows`.
- For state schema evolution, set `spark.sql.streaming.stateStore.encodingFormat` to `avro` and evolve case classes additively.
- Follow `spark-guidelines` operator migration checklist when switching from `flatMapGroupsWithState` to `transformWithState`.

## Aggregations & Joins

- Use **`groupByKey` + `mapGroups` / `transformWithState`** for per-key stateful logic; avoid `groupBy` + UDF when built-in aggregations suffice.
- Typed **`Aggregator`** implementations for custom aggregate functions that must be reusable and Catalyst-serializable.
- Window functions via **`Window.partitionBy(...).orderBy(...)`** import — do not reimplement ranking with self-joins.

## CDC Dedup & MERGE

Follow `spark-guidelines` MERGE tie-break policy. Idiomatic forms:

- **Silver dedup:** `row_number()` over `Window.partitionBy($"order_id").orderBy($"event_timestamp".desc, $"ingest_timestamp".desc)`, then keep `=== 1`.
- **MERGE tie-break:** mirror the same ordering in the `whenMatched` update (Delta `DeltaTable.merge` or Iceberg `MERGE INTO`).

## Project Structure

- Separate **pipeline orchestration** (main/app object, CLI args, SparkSession builder) from **transform definitions** (pure `DataFrame => DataFrame` functions in a `transforms` package).
- Configure `SparkSession` once; pass `SparkSession` explicitly to transform functions rather than implicit globals.
- Match the repo's effect system if present (e.g. `IO` for orchestration), but keep Spark actions (`count`, `write`) at the outermost edge — Spark manages its own execution model internally.

## Anti-Patterns

- `collect`, `take`, or `toLocalIterator` on large datasets in production paths
- `var` and mutable collections inside UDFs or StatefulProcessors
- `implicits._` wildcard in library code — import only the encoders you need
- Driver-side `parallelize` of large in-memory collections
- Exception-driven control flow in UDFs — return `Option`/`Either` columns or filter invalid rows at silver

## Verification

- `sbt test` with a local Spark session or `spark.master=local[*]` in test config
- `scalafmtCheckAll` and compile with `-Xfatal-warnings` when the repo enforces them
- For streaming: test with `Trigger.AvailableNow` and a temp checkpoint dir cleaned in fixtures

## Output Contract

When implementing, compose pipelines as named transform stages, keep column logic in Catalyst where possible, and record proof commands. When reviewing, flag RDD usage, driver-side collects, untyped string column access, and legacy `flatMapGroupsWithState` that should migrate to `transformWithState`.
