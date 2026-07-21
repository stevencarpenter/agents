# Bronze Orders Data Contract

## Table: `bronze.orders`

| Column | Type | Notes |
|--------|------|-------|
| order_id | string | Business key, not null |
| customer_id | string | FK to customers |
| product_id | string | |
| quantity | int | Must be > 0 |
| unit_price | decimal(10,2) | |
| event_timestamp | timestamp | Event time of this change |
| event_type | string | CREATE, UPDATE, CANCEL |
| ingest_timestamp | timestamp | Processing time at bronze landing |

## Semantics

- Bronze is append-only CDC landing from Kafka. Multiple rows per `order_id` are expected.
- Silver should hold **one current row per order_id** reflecting the latest event by `event_timestamp`.
- **Tie-break:** when two bronze rows share the same `order_id` and `event_timestamp`, keep the row with the **latest `ingest_timestamp`** (processing-time arrival order).
- CANCEL events set `status = CANCELLED`; CREATE/UPDATE set `status = ACTIVE`.
- Silver table: `silver.orders` on Delta Lake path `s3://lakehouse/silver/orders/`

## SLAs

- Freshness: silver within 15 minutes of bronze
- Replay: reprocessing any 7-day bronze partition must produce identical silver state

## Quality checks at silver boundary

- `order_id` not null and unique in silver
- `quantity` > 0 for non-CANCELLED rows
- `event_timestamp` not in the future (> 1 hour ahead of now)
