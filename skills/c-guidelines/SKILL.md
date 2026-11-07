---
name: c-guidelines
description: Use when writing, reviewing, or designing C code (C17 or C23) where memory safety, integer handling, header and ABI design, FFI with Rust or C++, build flags, or tests matter.
---

# C Guidelines

Use this as the shared C language rubric for agents. Prefer repo-local conventions when they are deliberate and documented. Push back when they produce fragile code or undefined behavior. The compiler accepting code is not evidence that the code is correct.

## Source Of Truth

- SEI CERT C Coding Standard: https://wiki.sei.cmu.edu/confluence/display/c/SEI+CERT+C+Coding+Standard
- ISO C17 (ISO/IEC 9899:2018) and the C23 working draft n3220: https://www.open-std.org/jtc1/sc22/wg14/www/docs/n3220.pdf
- MISRA C, only where the repo adopts it. Follow the adopted edition and its recorded deviations.
- The repo's compiler flags, language standard setting, and CI configuration. These decide which features are allowed.

## Core Rubric

- Ownership: state in the header comment who allocates, who frees, and how long a pointer stays valid. Mark each pointer as borrowed or owned. Pair every `_create` with a `_destroy` or `_free` function.
- Bounds: pass `(const uint8_t *data, size_t len)` for binary data. Never rely on a trailing NUL for non-text data. Check `len` before every read and write.
- Integers: unsigned arithmetic wraps. Signed overflow is undefined behavior. Check before you add or multiply `size_t` values. Use checked helpers such as `__builtin_mul_overflow` or a small portable wrapper. Beware integer promotion and mixed signed/unsigned comparison.
- Strings: use `snprintf` and a bounded copy that reports truncation. Never use `strcpy`, `strcat`, `sprintf`, or `gets`. Do not use `strtok` in library code. Use `strtok_r` or manual scanning.
- Errors: return an `int` or enum status and write results through an out-parameter. Do not use magic return values such as `-1` or `NULL` for two meanings. Set `errno` only for libc-style APIs, and read it right after the failing call.
- Const and restrict: use `const` on every read-only pointer parameter. Use `restrict` only when the non-aliasing contract is true and documented.
- Opaque types: expose `typedef struct foo foo;` in the header and define the struct in the `.c` file. Callers then cannot depend on layout.
- Linkage: mark every file-local function and object `static`. Declare only the public API in headers.
- Initialization: use designated initializers (`{ .len = 0, .data = NULL }`). Zero-initialize structs that cross a trust boundary.
- Enums and switches: handle every enumerator in a `switch`. Keep `-Wswitch` active and avoid a `default:` that hides new values. Validate enum values that arrive from outside the program.
- Headers: use include guards or `#pragma once` as the repo does. Make each header self-contained. Put no function definitions in headers except `static inline`. Wrap declarations in `#ifdef __cplusplus extern "C" { #endif`. Use `<stdint.h>` and `<stdbool.h>` types (C23 has `bool` as a keyword).
- Memory: use `calloc(n, size)` or an overflow-checked `n * size` for arrays. Do not use VLAs in library code. Check every allocation result. Set a pointer to `NULL` after `free` when the pointer stays in scope. State whether `_free(NULL)` is allowed (it should be).
- Concurrency: use C11 `<threads.h>`, `<stdatomic.h>`, or pthreads as the repo does. Every shared mutable object needs one named lock or an atomic. A data race is undefined behavior.
- Undefined behavior: know the classes. They are out-of-bounds access, use after free, double free, uninitialized reads, signed overflow, invalid shifts, null dereference, strict aliasing violations, misaligned access, and unsequenced modification. Find them with warnings, sanitizers, and tests, not by inspection alone.
- Smallest coherent diff. No drive-by reformatting, renames, or include reordering outside the change scope.

## ABI And FFI Rubric

- Keep the public struct layout stable. Account for padding and alignment. Use fixed-width types, not `int`, `long`, or `bool` in `#[repr(C)]` mirrors.
- Do not put bitfields, unions with unclear active members, or `long double` in a boundary struct.
- Version boundary structs: put `uint32_t size` or `uint32_t version` first, and only append new fields.
- A callback takes a `void *user_data` pointer. Document which thread calls it, whether it may call back into the library, and how long `user_data` must live.
- Document string encoding (UTF-8, not NUL-terminated, or both) and who frees returned buffers. Memory must be freed by the allocator that created it. Export a `_free` function for library-allocated buffers.
- A header that mirrors Rust `#[repr(C)]` types must match field order, sizes, and enum underlying types. Prefer `cbindgen` output and compare it to the committed header.
- Never let a `longjmp` or a C++ exception cross the boundary. Rust panics must not unwind into C.

## Anti-Slop Checklist

Reject or fix these generated-code patterns on sight:

- `malloc(n * sizeof(T))` with an unchecked multiplication.
- `strcpy`, `strcat`, `sprintf`, `gets`, or `scanf("%s")` into a fixed buffer.
- Casting away `const` to silence a warning.
- Ignoring the return value of `malloc`, `fopen`, `fread`, `snprintf`, or `pthread_*`.
- `int` used for sizes, lengths, or indexes where `size_t` is correct.
- `char` used for bytes. Use `uint8_t` or `unsigned char`.
- Comparing a `size_t` against a possibly negative `int`.
- `memcpy` or `memset` with an unvalidated length, or on overlapping regions (use `memmove`).
- `sizeof(ptr)` where `sizeof(*ptr)` or the array size was meant.
- Magic numbers for buffer sizes with no named constant or check.
- Cleanup duplicated on every error path instead of one `goto cleanup` label, or leaked on one path.
- Comments that restate the code (`/* increment i */`) instead of stating ownership, units, or invariants.
- Public functions missing `static` when they are file-local.
- A `#define` macro that evaluates its argument twice where a `static inline` function works.
- `assert` used for input validation. `NDEBUG` removes it.

## Verification

Use exact repo-native gates first: the documented `make`, `cmake --build`, `ctest`, or CI script. Do not install tooling speculatively. Use these only when the repo has them or the change justifies them:

- Compiler warnings: `-Wall -Wextra -Werror -Wconversion -Wshadow` (also `-Wformat=2 -Wstrict-prototypes` when the repo allows).
- Static analysis: `clang-tidy`, `cppcheck`, or the compiler's `-fanalyzer` (GCC).
- Runtime checks: build tests with `-fsanitize=address,undefined`. Use ThreadSanitizer (`-fsanitize=thread`) or `valgrind` for threaded or leak questions. ASan and TSan cannot run in the same binary.
- Tests: use the repo's framework (Unity, CMocka, Check, or plain `assert` programs). Cover error paths and boundary lengths (0, 1, max, max plus 1).
- Fuzzing: `libFuzzer` or AFL++ for parsers, when configured.
- Rust-generated headers: regenerate with `cbindgen` and diff the result against the committed header. Add a layout test (`sizeof`, `offsetof`) on both sides.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **Fixing a warning with a cast.** A cast hides the conversion bug. Fix the type or add a range check.
- **"It works with -O0."** Optimizers exploit undefined behavior. Test at the release optimization level too.
- **Using `NULL` or `-1` as both error and valid value.** Return a status code and use an out-parameter.
- **Sanitizer clean means safe.** Sanitizers see only executed paths. Add inputs at length boundaries and fuzz parsers.
- **`strncpy` as a safe `strcpy`.** It may leave the buffer unterminated and pads with zeros. Use `snprintf` or a checked copy.
- **Freeing a pointer the library does not own.** Across an FFI boundary, free only with the allocator that made the memory.
- **`packed` structs to match a layout.** Unaligned member access is undefined behavior on some targets. Use explicit padding fields and `_Static_assert` on size and offsets.
- **Callback invoked on an unknown thread.** Without a documented thread, `user_data` access races. Require a thread contract or internal locking.

## Output Contract

When reviewing, lead with severity-ranked findings. Put memory-safety and undefined-behavior defects before design and style. Give file and line evidence, the failing input or state, and the safer direction.

When implementing, make the smallest coherent change, add or update tests for error paths and boundaries, and record the exact build and test commands you ran.
