---
name: cpp-guidelines
description: Use when writing, reviewing, or designing C++20 or C++23 code where ownership, lifetimes, undefined behaviour, API shape, threading, ABI and FFI boundaries, build configuration, performance, or tests matter.
---

# C++ Guidelines

Use this as the shared C++ language rubric for agents. Prefer repo-local conventions when they are deliberate and documented. Push back when they produce unsafe, fragile, or undefined behaviour.

Unreal Engine C++ has its own conventions (UObject lifetime, `TArray`, `FString`, UHT macros, no exceptions). Inside Unreal modules, the `unreal-guidelines` skill takes precedence over this rubric where the two conflict. Route Unreal work there first.

## Source Of Truth

- C++ Core Guidelines: https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines
- cppreference (language and library semantics): https://en.cppreference.com/
- The repo's `.clang-tidy`, `.clang-format`, and CMake presets (`CMakePresets.json`). These define the local gates.
- The repo's documented error policy (exceptions, `std::expected`, or status codes). Follow it. Do not mix policies in one module.

Target the language standard the build sets (`CMAKE_CXX_STANDARD` or `-std=`). Do not use C++23 features in a C++20 build.

## Core Rubric

- Ownership: use RAII for every resource. Use `std::unique_ptr` by default. Use `std::shared_ptr` only for genuinely shared lifetime. A raw pointer or reference is a non-owning observer.
- Borrowed inputs: take `std::span<const T>`, `std::string_view`, or `const T&`. Do not store a view past the lifetime of its owner.
- Value semantics: prefer value types. Follow the rule of zero. If a type needs a destructor, copy, or move, define all five or delete them deliberately.
- Const-correctness: mark members, parameters, and locals `const` when they do not change. Do not cast away `const`.
- Strong types: use `enum class` and small wrapper types when they prevent a concrete mix-up (ids, units, indexes). Do not wrap ordinary values without a reason.
- Errors: follow the repo policy. `std::expected<T, E>` or a domain error type suits recoverable failure on hot or exception-free paths. Exceptions suit exceptional failure where the repo allows them. Never throw across a C boundary.
- Annotate with `[[nodiscard]]` on functions whose result must be checked (errors, handles, factories). Use `noexcept` only when the guarantee is real.
- Use `constexpr` and `consteval` where compile-time evaluation is natural. Use a template or `constexpr` function instead of a macro.
- Generics: use concepts and `requires` clauses. Do not add new SFINAE (`enable_if`) in C++20 code.
- Algorithms: prefer `std::ranges` algorithms and views over hand-written index loops when they read clearer. Do not chain views whose lifetime rules you cannot state.
- Casts: use `static_cast` and friends with a reason. No C-style casts. `reinterpret_cast` needs a stated layout invariant.
- Memory: no raw `new` or `delete`, no `malloc` in C++ code outside a wrapper. Use `std::make_unique` and `std::make_shared`.
- Headers: each header is self-contained and has include guards or `#pragma once` as the repo does. Include what you use. Forward-declare when it avoids a heavy include. Keep `using namespace` out of headers.
- Undefined behaviour classes to check every time: dangling lifetime, strict aliasing, signed overflow, uninitialized reads, out-of-bounds access, ODR violations, data races, and use after move.
- ABI and FFI: expose C boundaries as `extern "C"` with plain-old-data types. Mirror layouts with `static_assert` on `sizeof` and `offsetof`. Keep hand-written C headers in sync with the C++ definition. Catch every exception at the boundary. For Rust interop, match `#[repr(C)]` layouts and document who frees each allocation.
- Threading: prefer `std::jthread` with `std::stop_token`. Use atomics with an explicit memory order and a stated reason for anything weaker than `seq_cst`. Do not hold a lock across a blocking call or a callback into unknown code.
- Performance: measure first. Then fix data layout, hidden copies, and allocations. Pass by `const&` or view, move on sink parameters, and `reserve` when the size is known.
- Keep the diff small. No drive-by renames, include reshuffles, or formatting churn outside the change scope.

## Anti-Slop Checklist

Reject or fix these debt patterns on sight, whether writing or reviewing:

- Raw `new`/`delete` or `malloc`/`free` where a smart pointer or container works.
- `std::shared_ptr` used to avoid deciding who owns an object, or `shared_ptr` cycles with no `weak_ptr`.
- Returning or storing `std::string_view`, `std::span`, or an iterator that points into a temporary or a container that may reallocate.
- C-style casts, and `const_cast` used to silence a const error.
- Macros for constants, inline functions, or type switches when `constexpr`, a template, or `enum class` works.
- Uninitialized members or locals. Initialize at declaration. Use member initializers.
- Missing `[[nodiscard]]` on error-returning or handle-returning functions, and ignored `std::expected` results.
- Single-argument constructors without `explicit`. Implicit conversions that hide cost or failure.
- Copying where a move or reference suffices: by-value `const` parameters of large types, `return std::move(local)` that blocks copy elision.
- `catch (...)` that swallows errors, and empty `catch` blocks.
- Header-level `using namespace`, non-inline function definitions in headers, and missing include guards.
- Virtual functions in a base class with a non-virtual public destructor, or missing `override`.
- Index loops with `int` over `size()` (signed/unsigned mismatch) where a range-for or algorithm fits.
- Commented-out code, `TODO` stubs, and dead branches left in a delivered change.
- Comments that restate the signature. Comments should carry ownership, lifetime, thread, or error contracts.

## Verification

Use exact repo-native gates first: the configured CMake preset, `cmake --build`, and `ctest --output-on-failure`. Use `compile_commands.json` as the input for tooling.

Run these only when the repo configures them or the change justifies them. Do not install tooling speculatively:

- `clang-format --dry-run --Werror` for formatting.
- `clang-tidy -p <build-dir>` with the repo's `.clang-tidy` for static checks.
- `cppcheck` when the repo uses it.
- `-fsanitize=address,undefined` build for memory and UB bugs in any touched ownership or pointer code.
- `-fsanitize=thread` (TSan) build for threading changes. Do not combine TSan with ASan.
- GoogleTest or Catch2, whichever the repo uses, run through `ctest`.
- `-Wall -Wextra -Wpedantic` and warnings-as-errors when the repo sets them.
- Valgrind (Linux) when sanitizers are unavailable.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **Dangling view or reference**: a `string_view`, `span`, or reference into a temporary, a moved-from object, or a reallocating container. The safer direction is to own the data (`std::string`, `std::vector`) or extend the owner's lifetime.
- **Exception across a C boundary or thread entry**: an exception escaping an `extern "C"` function or a `std::thread` body ends the program or is UB. Catch at the boundary and convert to an error code.
- **Lock held across a callback or blocking call**: this deadlocks or inverts priority. Copy the data under the lock, release it, then call out.
- **Atomics with relaxed order by guesswork**: weaker ordering without a happens-before argument is a latent race. Use `seq_cst` until the reason for weaker order is written down.
- **`shared_ptr` from `this`**: calling `shared_ptr<T>(this)` double-owns the object. Use `enable_shared_from_this` or redesign ownership.
- **Signed overflow or unchecked narrowing**: signed overflow is UB, and narrowing hides truncation. Use checked arithmetic, unsigned types for bit work, or a range check before the cast.
- **ODR and header drift**: two definitions of an inline function or struct differ across translation units, or a C header no longer matches the C++ layout. Add `static_assert` layout checks and one source for each definition.
- **Moved-from use**: reading an object after `std::move` relies on an unspecified state. Reassign it or do not touch it.
- **Iterator invalidation**: `push_back`, `erase`, or `insert` while iterating. Collect changes first or use the erase-remove idiom or `std::erase_if`.

## Output Contract

When reviewing, lead with severity-ranked findings and concrete file and line evidence. Each finding states the violated invariant or undefined behaviour class, why the current shape is risky, and the safer C++ direction. Separate verified facts from inferences.

When implementing, make the smallest coherent change, add or update tests for observable behaviour, and record the exact build and test commands that proved it.
