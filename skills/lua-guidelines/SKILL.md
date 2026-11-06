---
name: lua-guidelines
description: Use when writing, reviewing, or designing Lua 5.4 or LuaJIT code, especially game scripting, modding APIs, sandboxed scripts, data-definition tables, or the C API boundary of an embedded interpreter.
---

# Lua Guidelines

Use this as the shared Lua rubric for agents. Prefer repo-local conventions when they are deliberate and documented. Push back when they cause globals, silent failures, or an unsafe host boundary.

## Source Of Truth

- Lua 5.4 Reference Manual: https://www.lua.org/manual/5.4/
- Programming in Lua, 4th edition (Roberto Ierusalimschy)
- LuaJIT documentation, including FFI, extensions, and NYI list: https://luajit.org/
- lua-users wiki style guide: http://lua-users.org/wiki/LuaStyleGuide
- The repo's `.luacheckrc`, formatter config, and test runner.

Identify the target runtime first: PUC Lua 5.4, Lua 5.3, Lua 5.1, or LuaJIT (5.1 semantics plus extensions). Do not write code that depends on features the target lacks.

## Core Rubric

- **Dialects.** LuaJIT has no integer subtype, no `//`, no native bit operators (use `bit.*`), and no `<close>` or `<const>`. It has `goto` and the FFI. Lua 5.4 has integers, `//`, `&`, `|`, `~`, `<<`, `>>`, `goto`, `<close>`, and `<const>`. Write to the lowest common denominator only when the code must run on both.
- Declare every variable `local`. A global is allowed only for a documented host-provided name. Keep module state in locals.
- Use the module pattern: build a local table `M`, add functions, and `return M`. Do not call `module()` or set globals from a module. In 5.2 and later, replace the environment with `_ENV`. In 5.1 and LuaJIT, use `setfenv`.
- Tables have an array part and a hash part. `#t` is only defined for sequences without holes. Never use `#` on a table that may contain `nil` between elements. Track an explicit count or use `table.pack` and `.n`.
- Use `t[#t + 1] = v` or `table.insert(t, v)` to append. Use `table.remove` only when order must shift. `ipairs` stops at the first `nil` and is ordered. `pairs` order is unspecified and can change between runs. Do not assign new keys to a table during `pairs`. Assigning `nil` to an existing field is allowed.
- Metatables: keep `__index` chains short (each level costs a lookup). Use `rawget` and `rawset` inside `__index` and `__newindex` to avoid recursion. Use `__close` (5.4) for scoped cleanup. Do not rely on `__gc` for timely release. Use weak tables (`__mode = "k"` or `"v"`) for caches, and remember that strings and numbers are never collected from weak tables.
- Closures capture variables, not values. A loop variable is fresh per iteration, but an outer local is shared. Avoid creating closures in hot loops.
- Errors: use `error(value, level)`. Raise a table with a `code` and `message` when callers must branch. Use `pcall` when the failure is handled. Use `xpcall` with `debug.traceback` as the handler when the trace is needed. Never discard a `pcall` result. Re-raise what you cannot handle. Use `assert` for invariants and note that its message argument is built eagerly.
- Coroutines sequence work such as cutscenes and AI. Yield across `pcall` works in 5.2 and later and in LuaJIT 2.1, not in 5.1. A coroutine that errors is dead, so check the `resume` result. LuaJIT cannot yield across a C function boundary (a `lua_call` from C or an FFI callback).
- Strings are immutable and interned (short strings). Each `..` creates a string. Build output with a table of parts and `table.concat`. Lua patterns are not regex: no alternation, and `-` is a lazy quantifier. Use `%` to escape magic characters. Use `string.format` with `%q` for safe quoting.
- Numbers: 5.4 distinguishes integer and float subtypes. `3 // 2` is `1`, `3 / 2` is `1.5`, and `math.type` tells them apart. Use `math.tointeger` for exact conversion. `0/0` is NaN and `nan ~= nan`, so never use NaN as a table key (it raises an error). Float to string formatting differs (`1.0` versus `1`).
- Varargs: use `select('#', ...)` for the true count, because `nil` may be present. Use `table.pack(...)` to keep `nil` values. `table.unpack` needs an explicit upper bound for tables with holes.
- Validate types at API boundaries with `type()` or a small checker, and fail with a message that names the argument and the expected type. Use `error(msg, 2)` so the position points to the caller.
- Data-definition tables are schemas. Validate required fields, types, ranges, and unknown keys at load time. Report the file and the field path. Freeze loaded definitions with a read-only proxy when scripts must not mutate them.
- Make the smallest coherent diff. No drive-by renames or formatting churn outside the change scope.

## Performance

- Measure first. Profile with the engine's profiler, `os.clock`, or LuaJIT's `-jp`.
- Avoid table creation in per-frame loops: reuse tables, clear them in place, or pool them. Preallocate with `table.move` or a constructor of known size, or `table.new` on LuaJIT.
- Cache hot globals and fields in locals (`local floor = math.floor`). A local lookup is a register access.
- Avoid `..` in loops. Avoid `string.format` and `tostring` on hot paths when a cached string works.
- LuaJIT: stay on traced paths. Avoid NYI builtins in hot code (for example `string.gsub` with a function replacement, `coroutine` calls, and `unpack` with large counts). Check with `-jv` or `-jdump`. Use `jit.off(fn)` for cold or branchy code that causes trace aborts. Prefer `ffi.new` arrays for numeric buffers.
- Tune the GC only with evidence. In 5.4 choose between `collectgarbage("incremental")` and `"generational"`. Call `collectgarbage("step")` during idle frames instead of full collects.

## C API And Embedding

- Stack discipline: every push needs a pop. Call `lua_checkstack` or `luaL_checkstack` before pushing many values. Use `lua_gettop` to verify balance in tests. Convert negative indices with `lua_absindex` before pushing more.
- Validate arguments with `luaL_check*` and `luaL_opt*`. Use `luaL_argerror` and `luaL_error` for failures. These longjmp (or throw in C++ builds), so do not leave C++ objects with destructors live on the frame, and do not call them while holding a resource that needs release.
- `lua_tolstring` pointers are valid only while the string value stays on the stack or reachable. Copy if you need it longer. `lua_tostring` on a number converts it in place and confuses `lua_next`.
- Userdata: create with `lua_newuserdatauv`, attach a metatable by `luaL_setmetatable`, test with `luaL_checkudata`. Put cleanup in `__gc`. `__gc` can run after the owning engine object dies, so use a validity flag or handle ids. Never store a raw pointer to a Lua-owned value in C.
- Registry: pin a Lua value with `luaL_ref` and release it with `luaL_unref`. A leaked ref is a leak of the value. Upvalues on `lua_pushcclosure` hold per-function state.
- Call Lua with `lua_pcall` and a message handler that adds a traceback. Never use unprotected `lua_call` from the host except inside a protected context. Never call into Lua from a signal handler. Set a flag and process it in the main loop.
- A `lua_State` is not thread safe. Use one state per thread, or serialize access. `lua_newthread` creates a coroutine state that shares the global state, so it is not a way to get parallelism. Anchor the thread object so it is not collected while in use.
- Sandbox untrusted scripts by building a restricted environment table with an allowlist of functions. Do not expose `os`, `io`, `debug`, `package`, `dofile`, `loadfile`, or `require` of arbitrary paths. Use `load(chunk, name, "t", env)` with mode `"t"` so precompiled bytecode is rejected. Block `string.rep` abuse and `setmetatable` on shared strings. Expose a metatable-protected string library.
- Limit resources: use `lua_sethook` with `LUA_MASKCOUNT` to bound instructions, and a custom allocator passed to `lua_newstate` to cap memory. Use the hook to raise an error, never to continue silently. LuaJIT has no reliable count hook inside compiled traces, so use `jit.off` for untrusted code or run it in a separate process.
- Hot reload: clear `package.loaded[name]` and re-`require`. Keep state in a separate table that survives reload, and migrate it with a versioned function. Re-register callbacks after reload. Remove old event handlers, or they run twice. Do not reload while a coroutine from the old module is suspended unless it is discarded.

## Anti-Slop Checklist

Reject or fix these patterns on sight, whether writing or reviewing:

- Implicit globals from a missing `local`, including loop variables and function names.
- `#t` on a table with holes or `nil` entries, and `table.insert(t, pos, nil)`.
- `pcall(f)` with the result ignored, or `if not ok then end`, or an error converted to `nil` with no log.
- `error("message")` strings where callers need a code, and error tables with no message.
- Using `pairs` where order matters, and mutating a table while iterating it.
- String building with `s = s .. x` in a loop.
- `tostring(x) == "nil"` style checks, and comparing floats with `==` after arithmetic.
- `load(str)` of data from users or the network without a sandbox environment and a size limit.
- Methods called with `.` instead of `:` (or the reverse) in a class pattern.
- `require` of a path built from user input.
- Deep `__index` inheritance chains used for plain data.
- Comments that restate the code, and commented-out blocks left in delivered changes.
- A module that sets globals or mutates `string`, `table`, or `math` for the whole process.

## Verification

Use exact repo-native gates first. Typical gates are `luacheck .` (with the repo's `.luacheckrc`), the configured formatter check (`stylua --check .` or `lua-format`), and the configured test runner (`busted` or the repo's script).

Reach for these only when the repo has them or the change justifies them. Do not install tooling speculatively:

- `lua -e 'require("mod")'` or `luajit -e ...` as a smoke run of the changed module on the target runtime.
- `luajit -jv script.lua` to list trace aborts, and `-jp` for a sampling profile.
- A build of the host with AddressSanitizer and UBSan when auditing C bindings.
- `lua_gettop` assertions in binding tests, and a loop that creates and destroys the bound object many times.
- `collectgarbage("count")` before and after a loop to check for leaks.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **Sandbox by blocklist.** Removing `os.execute` from a full `_G` leaves `io`, `load`, `debug`, and string metatable escapes. Build an allowlist environment instead.
- **`load` of text without a mode.** `load(s)` accepts bytecode, which can crash the VM. Pass mode `"t"`.
- **Instruction hook on LuaJIT.** Count hooks do not fire inside compiled traces. Use `jit.off`, an allocator limit, or process isolation.
- **`#` on a sparse table.** The result is any valid border. Use an explicit count.
- **Error thrown through C++ frames.** `luaL_error` longjmps over destructors. Compile Lua as C++ or release resources before raising.
- **`__gc` touching freed host objects.** Finalizers run late and in any order. Use handle ids and a validity check.
- **Hot reload leaking handlers.** Old closures stay registered. Unregister before reload.
- **Caching with strong references.** A cache keyed by object keeps it alive. Use weak keys or values.

## Output Contract

When reviewing, lead with severity-ranked findings and concrete file and line evidence. Each finding explains why the current Lua shape is risky and names the safer direction. State the target runtime you assumed.

When implementing, make the smallest coherent change, add or update tests for observable behavior, and record the exact proof command.
