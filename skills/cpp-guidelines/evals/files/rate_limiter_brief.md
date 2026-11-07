# Rate limiter library: API brief

A C++23 library, `ratelimit`, used by several services and by one Rust service through a C ABI.

## Requirements

- Token bucket and sliding window algorithms. More algorithms (leaky bucket) are planned.
- Each limiter has a capacity, a refill rate, an optional burst size, an optional clock source (tests need a fake clock), and an optional name used in metrics.
- `try_acquire(n)` is called on the hot path from many threads. It must not allocate and must not throw.
- Callers need to tell apart: allowed, denied with a retry-after duration, and invalid request (n larger than capacity).
- Limiters are shared by many request handlers. Handlers must not be able to destroy a limiter that another handler still uses.
- Configuration comes from user input (YAML). Bad values (zero rate, negative capacity) must be rejected, not clamped silently.
- The Rust service links the library through a C API. The C header is hand-written and must stay in sync.
- The repo builds with C++23. Its documented error policy: no exceptions on the hot path, `std::expected` for fallible construction.

## Known consumer snippet

```cpp
auto limiter = ratelimit::TokenBucket::create({
    .capacity = 100,
    .refill_per_second = 50,
});
if (!limiter) { log(limiter.error()); return; }

auto decision = limiter->try_acquire(1);
if (decision.allowed()) { handle(request); }
else { reply_429(decision.retry_after()); }
```

## Deliverable questions

- How are units (tokens, durations, rates) kept from being mixed up?
- How does the library add algorithms and a metrics hook later without breaking ABI or API?
- What does the C API look like, and how does it avoid exceptions crossing the boundary?
