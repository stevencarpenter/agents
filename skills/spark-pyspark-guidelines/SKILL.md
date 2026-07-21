---
name: spark-pyspark-guidelines
description: Use when writing or reviewing idiomatic PySpark 4 code — typed DataFrames, pandas UDFs/Arrow, transformWithStateInPandas StatefulProcessor, StructType schemas, Pandas API on Spark, pytest fixtures, and Python packaging for Spark jobs. Trigger for PySpark, Python Spark ETL, Databricks notebooks in Python, or spark-submit Python pipelines even when "Spark" is not spelled out.
---

# Spark PySpark Guidelines

Language-specific Spark 4 rubric for Python agents. Always apply `spark-guidelines` first for engine-level pipeline design; use this skill for Python idioms. General Python style still applies — full type annotations, pytest over ad-hoc scripts, `pyproject.toml` packaging; for substantial non-Spark Python modules, defer to the python-implementer or python-reviewer agents, which carry the full `python-guidelines` rubric.

## Source Of Truth

- PySpark API docs: https://spark.apache.org/docs/latest/api/python/
- Structured Streaming `transformWithStateInPandas` guide
- The repo's `pyproject.toml` or `requirements.txt` — PySpark version, Python version, and test runner

## API Choice

- **DataFrame API (PySpark SQL)** is the default for all ETL. Do not use **RDD** in new Spark 4 pipeline code.
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
- For pandas UDFs, declare the return type explicitly and choose the form by **Python type hint** — not the removed `PandasUDFType` enum (deprecated in Spark 3.0, gone in 4): `def f(s: pd.Series) -> pd.Series` (scalar), `def f(it: Iterator[pd.Series]) -> Iterator[pd.Series]` (scalar-iterator), or `def f(v: pd.Series) -> float` (series-to-scalar, used with `groupBy().agg()`).

## Structured Streaming in Python

- Use **`transformWithStateInPandas`** with a class extending `StatefulProcessor`:
  - `init` — acquire `ValueState`, `ListState`, or `MapState` handles
  - `handleInputRows` — process each micro-batch
  - `close` — cleanup
- Migrate legacy **`applyInPandasWithState`** call sites to `transformWithStateInPandas` on Spark 4. (`flatMapGroupsWithState` is a Scala/Java typed-Dataset API with no PySpark equivalent — it does not appear in Python code.)
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
- **`groupBy(...).applyInPandas(func, schema)`** (the replacement for the removed `GROUPED_MAP` UDF) only when group-local pandas logic is required and cannot be expressed in SQL; prefer the iterator-of-DataFrame form to bound memory on skewed groups.
- Never mutate input pandas Series/DataFrames in place inside a UDF.
- Keep UDFs **deterministic and side-effect free** — no I/O, no global mutable state.

## Packaging & Session Lifecycle

- Build `SparkSession` in one place; pass it to transform functions or use a thin session factory in tests.
- For **`spark-submit`**, use `__main__` guards and argparse/typer for CLI — no hard-coded paths.
- In pytest, use a **session-scoped `SparkSession` fixture** with `local[*]` and reduced shuffle partitions (`spark.sql.shuffle.partitions=2` in tests).
- Clean up temp warehouse dirs and checkpoint paths in fixtures.

## Anti-Patterns

- `df.collect()`, `df.toPandas()`, or `df.first()` on large datasets in production paths
- Plain **non-Arrow Python UDFs** on hot paths — they serialize row-by-row
- `shell=True` or string-interpolated SQL with user input — use parameterized `spark.sql` with literals or DataFrame API
- Notebook-global mutable state reused across unrelated pipelines
- `repartition` without a measured reason — it forces a full shuffle

## Verification

- `pytest` or `unittest` with local Spark fixtures and small parquet/json fixtures in `tests/fixtures/`
- `ruff check` and `mypy` when the repo configures them
- For streaming tests: `Trigger.AvailableNow`, temp checkpoint dir, `memory` sink or foreachBatch collector

## Output Contract

When implementing, compose pipelines as typed transform functions, keep column logic in Catalyst where possible, and record proof commands. When reviewing, flag `collect`/`toPandas` on big data, legacy stateful APIs, untyped dict configs, and Python UDFs where SQL would suffice.
