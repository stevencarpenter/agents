---
name: sql-guidelines
description: Use when writing, reviewing, or optimizing SQL — query correctness, schema and migration design, index choices, or SQLite-specific patterns including FTS5.
---

# SQL Guidelines

Shared SQL rubric for agents, with SQLite depth. Read the affected tables, indexes, constraints, and callers before changing a query; expand the inspection when dependencies require it. Understand the access pattern before proposing an index.

## Source Of Truth

- The live schema: `SELECT name, sql FROM sqlite_master WHERE type IN ('table','index');` and `PRAGMA table_info(<t>);`
- SQLite docs for engine-specific behavior; the migration history for intended evolution

## Query Correctness

- Explicit `JOIN` syntax, never comma joins. Qualify every column with a table alias in multi-table queries.
- Prefer CTEs (`WITH …`) over correlated subqueries when it clarifies intent; avoid correlated subqueries inside loops.
- Handle NULLs deliberately. Use `COALESCE` only when the replacement matches domain semantics; missing data is not automatically zero or an empty string.
- In `GROUP BY`, include every non-aggregate column from `SELECT`.
- Use window functions (`ROW_NUMBER`, `LAG`, `LEAD`) for sequence/time analysis instead of self-joins.

## SQLite Specifics

- `INTEGER PRIMARY KEY` over rowid aliases. `STRICT` tables on SQLite ≥ 3.37. `WITHOUT ROWID` only for narrow natural-key tables.
- Enable `PRAGMA foreign_keys = ON` on connections that enforce foreign keys. Choose journal and synchronous modes from the concurrency and durability requirements; do not change database-wide settings during query review or read-only analysis.
- FTS5 over fts4: search with `WHERE fts MATCH '…'`, rank with `ORDER BY rank` (BM25 is built in — no separate `bm25()` needed). Join FTS to base tables on rowid via a CTE.
- Use `json_extract` / `json_each` to query JSON columns in-engine rather than parsing in the app layer.

## Index & Migration Discipline

- Add indexes for measured access patterns, considering selectivity and write cost. Use the engine's explain output before and after; a scan is not automatically a defect. Confirm workload coverage before declaring an index unused.
- Match the repository's migration and recovery policy. Use native column rename/drop when supported by the deployed SQLite version and dependency constraints; rebuild only for unsupported changes ([ALTER TABLE](https://www.sqlite.org/lang_altertable.html)). Backfill and validate before enforcing `NOT NULL`. Do not present a down migration as recovery for deleted data.

## Output Contract

When reviewing or optimizing, show the query, the problem, the corrected form, and the `EXPLAIN QUERY PLAN` evidence where relevant. For read-only analysis, prefer `PRAGMA query_only = ON` and limit exploratory result sets.
