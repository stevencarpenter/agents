# Clickstream Pipeline Design (proposed)

Author: platform team. Status: awaiting review before build.

## Storage

- Land raw events as **Parquet files** at `s3://lake/clickstream/raw/`, one folder per
  `user_id` so per-user lookups are fast: `raw/user_id=<uuid>/date=<yyyy-mm-dd>/part-*.parquet`.
- A nightly job rewrites the folder tree into `s3://lake/clickstream/clean/` (also Parquet,
  same user_id/date folder layout), applying type casts and dropping malformed rows.
- Analysts query `clean/` directly with ad-hoc SQL.

## Ingestion

- Kafka consumer appends every batch it receives to `raw/`. If the consumer crashes,
  the supervisor restarts it and it resumes from the last committed offset, re-appending
  any batch that was in flight.
- Batches are appended blind — no merge or dedup step. Duplicate events are assumed rare
  enough to ignore.

## Retention & maintenance

- We plan to move `clean/` to a table format next quarter; the runbook already schedules
  `VACUUM clickstream RETAIN 24 HOURS` daily for then, to keep storage flat.
- Finance re-runs last week's numbers from `clean/` for the monthly close and expects
  them to reproduce exactly.

## PII

- `clean/` keeps `email` and `ip_address` in the clear; the BI tool applies a masking
  expression in each dashboard query. Analysts with SQL access are trusted.

## Serving

- The `daily_active_users` dashboard scans all of `clean/` each morning and filters to
  yesterday in the WHERE clause.
