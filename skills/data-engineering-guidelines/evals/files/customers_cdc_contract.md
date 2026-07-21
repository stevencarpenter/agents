# Customers CDC Data Contract

## Source

Debezium change feed from the `customers` PostgreSQL table, delivered via Kafka topic
`crm.public.customers`. Envelope fields: `op` (c/u/d), `before`, `after`, `ts_ms`,
`lsn` (monotonic log sequence number).

## Payload schema (`after`)

| Column | Type | Notes |
|--------|------|-------|
| customer_id | string | Business key, not null |
| email | string | PII |
| tier | string | FREE, PRO, ENTERPRISE |
| country | string | ISO-3166 alpha-2 |
| updated_at | timestamp | Source-system event time |

## Semantics

- Silver must hold **one current row per customer_id** (SCD type 1).
- Deletes (`op = d`) must tombstone the silver row (`is_deleted = true`), not drop history from bronze.
- Two changes can share the same `updated_at`; `lsn` is the authoritative total order.

## SLAs

- Freshness: silver within 10 minutes of the source commit.
- Replay: reprocessing any 3-day bronze window must converge to identical silver state.

## Quality requirements (decide the action for each)

- `customer_id` not null
- `email` matches a syntactic email shape
- `tier` in the allowed set
- `country` is a known ISO code

## Governance

- `email` is PII: downstream consumers below the `analyst_pii` role must never see clear values.
