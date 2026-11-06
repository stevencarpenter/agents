# Brief: C header for the `meterlib` Rust static library

The Rust crate `meterlib` is built as a static library (`libmeterlib.a`) and linked into a C++17 host application on macOS and Linux. The host includes a hand-written header, `crates/meterlib/include/meterlib.h`. Design that header.

## Rust side (already written, `#[repr(C)]` where shown)

```rust
#[repr(C)]
pub struct MeterSample {
    pub timestamp_ms: u64,
    pub channel: u8,
    pub value: f64,
    pub flags: u16,
}

#[repr(C)]
pub enum MeterStatus { Ok = 0, InvalidArgument = 1, Closed = 2, Internal = 3 }

pub struct Meter { /* internal state, not repr(C) */ }

extern "C" {} // functions below are exported with #[no_mangle] pub extern "C" fn
```

Functions to expose:

1. Create a `Meter` from a UTF-8 config string (not guaranteed NUL-terminated, length known). Returns a handle.
2. Destroy a `Meter`.
3. Push a `MeterSample` into the meter.
4. Read a snapshot: fill a caller-provided array of up to N `MeterSample` values and report how many were written.
5. Get a human-readable description of the meter. The Rust side allocates the string. The host must read it and release it.
6. Register a callback that the meter calls when a threshold is crossed. The callback receives the sample that crossed. Rust may call it from an internal worker thread.
7. Report the library version.

## Constraints

- The host is C++17, so the header must compile as both C17 and C++.
- The struct `MeterSample` may gain fields in later releases. Old host binaries built against an older header must keep working with a newer library where practical.
- The host team already writes `meter_push(m, &sample)` and checks `== 0` for success in some existing code.
- Platforms: macOS (arm64) and Linux (x86_64, aarch64).

## Deliverables

- `outputs/meterlib.h`: the full header with doc comments for every ownership, thread, and encoding rule.
- `outputs/abi_notes.md`: the layout, versioning, and error-handling decisions, the layout checks you recommend on both sides, and how `cbindgen` output should be compared to the header.
