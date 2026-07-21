---
name: sql-guidelines
description: Use when writing, reviewing, or optimizing SQL — query correctness, schema and migration design, index choices, or SQLite-specific patterns including FTS5.
---

# SQL Guidelines

Shared SQL rubric for agents, with SQLite depth. Read the full schema and existing indexes before writing or changing queries; understand the access pattern before proposing an index.

## Source Of Truth

- The live schema: `SELECT name, sql FROM sqlite_master WHERE type IN ('table','index');` and `PRAGMA table_info(<t>);`
- SQLite docs for engine-specific behavior; the migration history for intended evolution

## Query Correctness

- Explicit `JOIN` syntax, never comma joins. Qualify every column with a table alias in multi-table queries.
- Prefer CTEs (`WITH …`) over correlated subqueries when it clarifies intent; avoid correlated subqueries inside loops.
- Handle NULLs deliberately with `COALESCE`; don't rely on accidental NULL propagation.
- In `GROUP BY`, include every non-aggregate column from `SELECT`.
- Use window functions (`ROW_NUMBER`, `LAG`, `LEAD`) for sequence/time analysis instead of self-joins.

## SQLite Specifics

- `INTEGER PRIMARY KEY` over rowid aliases. `STRICT` tables on SQLite ≥ 3.37. `WITHOUT ROWID` only for narrow natural-key tables.
- `PRAGMA foreign_keys = ON` at every connection — it's off by default. `WAL` journal mode + `PRAGMA synchronous = NORMAL` for concurrent readers.
- FTS5 over fts4: search with `WHERE fts MATCH '…'`, rank with `ORDER BY rank` (BM25 is built in — no separate `bm25()` needed). Join FTS to base tables on rowid via a CTE.
- Use `json_extract` / `json_each` to query JSON columns in-engine rather than parsing in the app layer.

## Index & Migration Discipline

- Index columns in `WHERE`, `JOIN ON`, `ORDER BY`. Covering indexes eliminate table lookups on hot paths. Run `EXPLAIN QUERY PLAN` before/after; a `SCAN TABLE` on a large table is the signal. Drop unused indexes — they cost write amplification.
- Migrations: ship reversible down-migrations. SQLite can't `DROP`/rename a column without a table rebuild. Backfill a new `NOT NULL` column with a default before removing the default.

## Output Contract

When reviewing or optimizing, show the query, the problem, the corrected form, and the `EXPLAIN QUERY PLAN` evidence where relevant. For read-only analysis, prefer `PRAGMA query_only = ON` and limit exploratory result sets.
