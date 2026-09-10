---
name: spark-pyspark-guidelines
description: Use when writing or reviewing idiomatic PySpark 4 code — typed DataFrames, pandas UDFs/Arrow, transformWithStateInPandas StatefulProcessor, StructType schemas, Pandas API on Spark, pytest fixtures, and Python packaging for Spark jobs. Trigger for PySpark, Python Spark ETL, Databricks notebooks in Python, or spark-submit Python pipelines even when "Spark" is not spelled out.
---

# Spark PySpark Guidelines

Language-specific PySpark rubric. Apply `spark-guidelines` for engine semantics and confirm the deployed version. Use typed functions and the repository's existing packaging and test framework; a notebook edit does not require a new package. For substantial non-Spark Python work, use the Python specialists.

## Source Of Truth

- PySpark API docs: https://spark.apache.org/docs/latest/api/python/
- Structured Streaming `transformWithStateInPandas` guide
- The repo's `pyproject.toml` or `requirements.txt` — PySpark version, Python version, and test runner

## API Choice

- Prefer the DataFrame API for ETL. Use RDDs only for a concrete unsupported operation or an existing library boundary; do not rewrite unrelated working code.
- **Pandas API on Spark (`pyspark.pandas`)** only when the team already standardized on it or for pandas-familiar exploratory transforms on moderate data — production pipelines should prefer the core DataFrame API for Catalyst optimization visibility.
- **pandas UDFs** (Arrow-optimized) when vectorized Python logic is unavoidable; plain Python UDFs only as a last resort on cold paths.

## Idiomatic Transforms

- Express transforms as **Column** expressions via `F.col`, `F.when`, `F.struct`, etc. Chain with `select`, `withColumn`, `filter`.
- Package reusable stages as functions `def clean_orders(df: DataFrame) -> DataFrame` — not copy-pasted notebook cells.
- Use **`df.transform(clean_orders)`** to compose pipeline stages functionally.
- Prefer built-ins (`from_json`, `explode`, `regexp_extract`, `aggregate`, `transform` for arrays) over UDFs.

## Schemas & Typing

- Define **`StructType` / `StructField`** explicitly for `from_json`, `createDataFrame`, and streaming sources — do not rely on inference in production.
- Type pipeline function signatures: `def enrich(df: DataFrame) -> DataFrame`.
- Use **`@dataclass` or TypedDict** on the driver for config objects; do not pass untyped dicts through pipeline boundaries.
- For pandas UDFs, declare the Spark return type and prefer supported Python type hints: `pd.Series -> pd.Series`, iterator forms, or series-to-scalar aggregates. `PandasUDFType` remains in Spark 4; type hints are preferred for new code, not a reason for an unrelated migration ([API source](https://spark.apache.org/docs/4.0.0/api/python/_modules/pyspark/sql/pandas/group_ops.html)).

## Structured Streaming in Python

- For arbitrary state unsupported by built-in streaming operators, use `transformWithStateInPandas` on compatible runtimes with a class extending `StatefulProcessor`:
  - `init` — acquire `ValueState`, `ListState`, or `MapState` handles
  - `handleInputRows` — process each micro-batch
  - `close` — cleanup
- Migrate `applyInPandasWithState` only when requested or required by a concrete lifecycle, compatibility, or state-management need. `flatMapGroupsWithState` is a Scala/Java API, not a PySpark call site.
- Follow `spark-guidelines` operator migration checklist when switching stateful streaming APIs.
- Set **`outputMode`**, **`timeMode`**, and **`outputStructType`** explicitly.
- Use **TTL and timers** via state handles rather than manual dict expiry in Python.
- For state schema evolution, enable Avro encoding on the state store and evolve dataclasses/Pydantic models additively.

## CDC Dedup & MERGE

Follow `spark-guidelines` MERGE tie-break policy. Idiomatic forms:

- **Silver dedup:** `row_number()` over `Window.partitionBy(business_key).orderBy(F.col("event_timestamp").desc(), F.col("ingest_timestamp").desc())`.
- **MERGE tie-break:** mirror the same ordering in `whenMatchedUpdate`.

## pandas UDF Discipline

- **Scalar pandas UDFs** for vectorized per-column transforms (Arrow batch processing).
- Use `groupBy(...).applyInPandas(func, schema)` only when group-local pandas logic cannot be expressed in SQL. The iterator-of-DataFrame form requires a runtime that supports it; otherwise whole groups must fit memory. `GROUPED_MAP` was not removed in Spark 4.
- Never mutate input pandas Series/DataFrames in place inside a UDF.
- Keep UDFs **deterministic and side-effect free** — no I/O, no global mutable state.

## Packaging & Session Lifecycle

- Build `SparkSession` in one place; pass it to transform functions or use a thin session factory in tests.
- For `spark-submit`, use a `__main__` guard and the existing CLI parser, or stdlib `argparse` when needed. Do not add Typer for a few arguments; keep environment-specific paths configurable.
- In pytest, use a **session-scoped `SparkSession` fixture** with `local[*]` and reduced shuffle partitions (`spark.sql.shuffle.partitions=2` in tests).
- Clean up temp warehouse dirs and checkpoint paths in fixtures.

## Anti-Patterns

- Unbounded `collect()`/`toPandas()` or oversized rows materialized on the driver. A bounded `first()`/`take(n)` is not equivalent to collecting the full dataset.
- Plain **non-Arrow Python UDFs** on hot paths — they serialize row-by-row
- `shell=True` or string-interpolated SQL with user input — use parameterized `spark.sql` with literals or DataFrame API
- Notebook-global mutable state reused across unrelated pipelines
- `repartition` without a measured reason — it forces a full shuffle

## Verification

- `pytest` or `unittest` with local Spark fixtures and small parquet/json fixtures in `tests/fixtures/`
- `ruff check` and `mypy` when the repo configures them
- For streaming tests: `.trigger(availableNow=True)`, a temporary checkpoint directory, and a bounded test sink or collector.

## Output Contract

When implementing, use typed transform functions where reusable stages exist, keep column logic in Catalyst, and record proof commands. When reviewing, flag unsafe driver materialization, unsupported APIs, unvalidated configs, and avoidable Python UDFs with evidence of the affected behavior.
