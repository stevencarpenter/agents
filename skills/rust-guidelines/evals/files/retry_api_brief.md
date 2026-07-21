# Brief: `retry` — public crate API for retrying fallible operations

We are publishing a small crate. Design the public API surface (no full implementation
of the timing internals required — `todo!()` bodies are fine where marked).

## Requirements

- Callers retry an async operation up to N times with a backoff strategy
  (fixed, exponential with jitter).
- Configuration has many optional knobs: max attempts, base delay, max delay,
  jitter on/off, an optional predicate deciding whether an error is retryable,
  an optional per-attempt timeout.
- Callers must be able to distinguish, programmatically: exhausted attempts
  (carrying the last error), a non-retryable error (carrying it), and timeout.
- The crate should work with any error type the caller uses.
- We expect to add a `tracing` integration later without breaking users, and more
  backoff strategies over time.

## Known consumer

```rust
let result = /* retry a reqwest call, 5 attempts, exponential backoff,
                only retry on 5xx, 2s per-attempt timeout */;
```

Deliverable: `outputs/lib.rs` (public types, traits, constructors, doc comments; internals
may be `todo!()`) and `outputs/api_notes.md` explaining the shape choices and the
semver/extension story.
