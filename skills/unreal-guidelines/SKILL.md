---
name: unreal-guidelines
description: Use when writing, reviewing, or designing Unreal Engine 5 C++ and project tooling where modules, reflection and GC, threading, Chaos physics, rendering, Niagara, editor automation, builds, or Rust/C FFI matter.
---

# Unreal Guidelines

Use this as the shared Unreal Engine rubric for agents. It targets UE 5.8 on macOS and Linux. Prefer repo-local conventions when they are deliberate and documented, but push back when they cause GC bugs, thread races, or unreproducible assets. Pair it with `cpp-guidelines` for language-level rules.

## Source Of Truth

- Epic C++ Coding Standard and UE 5.8 documentation: https://dev.epicgames.com/documentation/en-us/unreal-engine/
- UE 5.8 release notes: https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-8-release-notes
- Engine source under `Engine/Source` is the truth for API signatures and `UE_DEPRECATED` markers.
- The repo's `Build.cs`, `Target.cs`, `.uproject`, `.uplugin`, `Config/*.ini`, and justfile decide local conventions and gates.

Treat any feature, status, or deprecation absent from the release notes or the engine source as unverified, and say so.

## Core Rubric

- Modules: keep `PublicDependencyModuleNames` to modules whose types appear in public headers. Put everything else in `PrivateDependencyModuleNames`. Do not widen `PublicIncludePaths` to silence an include error.
- Keep `PCHUsage = UseExplicitOrSharedPCHs` and include what you use (IWYU). Do not include `CoreMinimal.h` plus broad engine headers in headers that a forward declaration satisfies.
- Plugins: declare module `Type`, `LoadingPhase`, and plugin dependencies in the `.uplugin`. Enable plugins in the `.uproject` only when used.
- Reflection: every `UObject` pointer member needs `UPROPERTY()` so the GC sees it. Use `TObjectPtr<T>` for member properties, `TWeakObjectPtr<T>` for non-owning references, and `TStrongObjectPtr<T>` for owners that are not `UObject`s. Use `AddToRoot` only as a last resort with a matching `RemoveFromRoot`.
- Never hold a raw `UObject*` in a `TArray`, `TMap`, or struct without `UPROPERTY`. Check with `IsValid(Obj)`, not `Obj != nullptr`, for objects that can be destroyed.
- Create objects with `NewObject`, `CreateDefaultSubobject`, or `SpawnActor`. Never use raw `new` on a `UObject`.
- Types: `FString` for text work, `FName` for identifiers, `FText` for user-visible text, `TArray`/`TMap`/`TSet` for containers, `TSharedPtr`/`TUniquePtr` for non-`UObject`s. `FVector`, `FRotator`, and `FTransform` are double precision in UE5. Use `float` only where an API requires it.
- Style: Epic prefixes A (actor), U (object), F (struct), E (enum), I (interface), T (template). Booleans start with `b`. Wrap literals in `TEXT()`. Declare a `DEFINE_LOG_CATEGORY` per module and use `UE_LOG` with a verbosity.
- Assertions: `check` halts and is for programmer invariants. `ensure` reports once and continues. `verify` keeps its expression in shipping builds. Never put required side effects inside `check`.
- Lifetime: do not call `GetWorld()` or touch other objects in a constructor. Use `PostInitializeComponents`, `BeginPlay`, and `EndPlay` for runtime setup and teardown. Register created components. Set `PrimaryActorTick.bCanEverTick` only when the actor needs `Tick`, and pick the lowest-cost tick group.
- Threading: mutate `UObject`s on the game thread only. Use `AsyncTask(ENamedThreads::GameThread, ...)` to return results. Prefer `UE::Tasks`, `AsyncTask`, or `ParallelFor` over raw `FRunnable`. Guard shared data with `FCriticalSection` plus `FScopeLock`, and keep the critical section short.
- Render thread: enqueue with `ENQUEUE_RENDER_COMMAND`, capture by value, and never capture a raw `UObject*` that the GC can free. Record work on `FRHICommandList` only on the render thread.
- Physics: Chaos uses centimetres. Convert forces from newtons by 100 and torques from N m by 10,000 (kg cm²/s²), never by 100. Use `AddForceAtLocation` for off-centre forces. With `bTickPhysicsAsync`, put physics input in `AsyncPhysicsTickActor` (`AsyncPhysicsTick`) at the fixed step, not in `Tick`. Check substepping settings and physical materials before tuning forces.
- Rendering: Nanite supports tessellation and displacement via materials, but cost depends on the material. Use `UMaterialInstanceDynamic` for per-instance parameters and create it once. Upload texture data with `UpdateTextureRegions` or a render command, and keep the source buffer alive until the command completes. Set Niagara user parameters with typed setters (`SetVariableFloat`, `SetVariableVec3`) on a cached component.
- Input: use Enhanced Input (`UInputAction`, `UInputMappingContext`). Do not add new legacy axis or action mappings.
- Framework: put rules in `AGameModeBase`, replicated match state in `AGameStateBase`, input in `APlayerController`, and possession in `APawn`. Use `UGameInstanceSubsystem`, `UWorldSubsystem`, or `ULocalPlayerSubsystem` for services with a clear lifetime.
- Replication: mark state `UPROPERTY(Replicated)` or `ReplicatedUsing`, implement `GetLifetimeReplicatedProps`, check `HasAuthority()` before mutating, and give each RPC `Server`, `Client`, or `NetMulticast` with `Reliable` only when loss is unacceptable. Validate `Server` RPC input.
- Assets: never hand-edit `.uasset` or `.umap`. Generate them with editor Python or Geometry Script, and commit the generator. Layer config as `Base` then `Default*.ini` then platform then `Saved`. Change project settings in `Default*.ini`.
- Version hygiene: check `UE_DEPRECATED` before using an API. Cite the 5.8 release notes for status. Label Experimental and Beta features as such in code review output.

## UE 5.8 Status Facts (from the release notes)

- Production Ready: Megalights, Movie Render Graph.
- Beta: Lumen Lite, Control Rig Physics.
- Experimental: MCP Server plugin, Fog Screen Space Scattering, Substrate NPR (Toon) Shading, Mesh Terrain, Fast Geometry Streaming, Procedural Vegetation Editor (Nanite foliage).
- Deprecated or renamed: `QueueSubtitle` (use `QueueSingleSubtitle`), `AllowRemoteNetworkService` (now `RemoteNetworkService`), `FastGeoStreaming.ini` (now `DefaultFastGeoStreaming.ini`). Removed: `EProxyCreationState::Pending`, `UFastGeoComponentEditorProxy`.

## Build And Editor Tooling

- Build with `Engine/Build/BatchFiles/Mac/Build.sh <Target>Editor Mac Development -Project=<x.uproject> -WaitMutex`. On Linux use the matching `Linux` script. Add `-NoUBA` when the Unreal Build Accelerator is unstable on that machine.
- Hot reload: an open editor makes UBT write a hot-reload module name that a `-game` run ignores. Delete `Binaries/` before a headless run after such a build.
- Live Coding changes function bodies only. Header, reflection, and `Build.cs` changes need a full build.
- `RunUBT.sh -mode=GenerateClangDatabase` writes `compile_commands.json` for clangd and CLion.
- Set `MACOSX_DEPLOYMENT_TARGET` to match `Engine/Config/Mac/Mac_SDK.json` when linking a static library.
- Do not default to Visual Studio or Windows-only tools.
- Editor scripts: `UnrealEditor-Cmd <project> -run=pythonscript -script=<file>`. Commandlets run with `-run=<Name>`. Automation tests use `IMPLEMENT_SIMPLE_AUTOMATION_TEST` or `IMPLEMENT_COMPLEX_AUTOMATION_TEST`.
- MCP Server plugin (Experimental): the editor serves MCP over HTTP with the meta-tools `list_toolsets`, `describe_toolset`, and `call_tool`. Call `describe_toolset` before `call_tool`. Data sent through it is Licensed Technology under the UE EULA.
- Headless checks: `UnrealEditor <project> -game -Windowed ...` exits 0 even after `RequestExitWithStatus(false, 1)`. Read the verdict from the log, not the exit code.

## FFI With Rust Or C

- Link one static library through `PublicAdditionalLibraries` and expose hand-written C headers through `PublicIncludePaths`. Wrap headers in `extern "C"`.
- No exceptions or panics cross the boundary. Return status codes and keep the error text retrievable.
- One `UObject` owns each foreign handle. Create it in `Initialize` and free it in `Deinitialize` or `BeginDestroy`. Never copy the handle.
- Keep the foreign API thread contract explicit and guard it with one lock when it is not thread safe.

## Anti-Slop Checklist

Reject or fix these patterns on sight, whether writing or reviewing:

- Raw `new` for a `UObject`, or `delete` on one.
- A `UObject*` member or container element without `UPROPERTY`, which the GC will free.
- `GetWorld()`, `GetOwner()`, or other object lookups in a constructor.
- `Tick` doing work that a timer, delegate, or event can do.
- `FindObject`, `LoadObject`, or `TActorIterator` by string or class in a hot path.
- `StaticLoadObject` or synchronous loads on the game thread during play instead of soft references and async load.
- Blueprint-only logic that C++ tests cannot reach, when the logic is core gameplay.
- `UE_LOG` without a category, or `UE_LOG` every frame at `Log` verbosity.
- Hard-coded asset paths in C++ without a `TSoftObjectPtr` or a config property.
- Float literals and `float` for world positions, which loses double precision.
- Hand-edited generated assets, or a generator that is not committed.
- Physics forces applied in `Tick` with `DeltaTime` scaling when the async physics step owns them.
- Creating `UMaterialInstanceDynamic` or Niagara components every frame.
- Comments that restate the declaration, and `UFUNCTION` or `UPROPERTY` specifiers with no reason.

## Performance

- Measure before changing. Use Unreal Insights (CPU, GPU, memory, loading traces), `stat unit`, `stat gpu`, `stat game`, and `ProfileGPU`.
- Report which of game thread, render thread, GPU, or RHI thread is the limit before proposing a fix.
- Look for Nanite and Lumen cost in `stat gpu`, draw calls in `stat rhi`, tick cost in `stat game`, and GC spikes in the Insights timing view.
- Do not tune from `stat fps` alone. Capture a trace on the target build configuration, not the editor.

## Verification

Use exact repo-native gates first (`just build`, `just check-all`, or similar recipes when present). Then use these when the repo has them:

- A UBT build of the editor target with the repo's exact flags.
- `clang-format` over `Source/**/*.h` and `*.cpp`, plus any lint gate (for example CRLF in tracked files).
- Automation tests run through `UnrealEditor-Cmd ... -ExecCmds="Automation RunTests <Filter>; Quit"`.
- Headless `-game` checks that read an explicit PASS or FAIL line from the log.
- Unreal Insights captures for performance claims.

Do not install tooling speculatively. State which checks were not run.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **`AddToRoot` to stop a GC crash** hides a missing `UPROPERTY`. Prefer `UPROPERTY`, `TStrongObjectPtr`, or a subsystem owner.
- **Touching a `UObject` from `AsyncTask` or the physics thread** races the GC and the game thread. Copy plain data under a lock and apply it on the game thread.
- **Forces in newtons on Chaos** are 100 times too weak. Scale to centimetre units and name the unit in the identifier.
- **Capturing `this` or a raw pointer in a render command or lambda** outlives the object. Capture values or a `TWeakObjectPtr`, and re-check validity.
- **Trusting `-game` exit code 0** reports success after a failure. Read the log verdict.
- **Editing generated `.uasset` files** cannot be reviewed or reproduced. Change the generator.
- **Panics or C++ exceptions across the FFI boundary** abort the editor. Catch at the boundary and return a status.
- **Depending on an Experimental feature** (MCP Server, Mesh Terrain) without a fallback or a stated risk. Mark the status and isolate the dependency.
- **Large `UpdateTextureRegions` every frame** with a freed or reused source buffer corrupts the upload. Keep the buffer alive until the cleanup callback and measure the upload size.

## Output Contract

When reviewing, lead with severity-ranked findings with file and line evidence. Each finding states the risk (crash, race, GC, cost, or reproducibility) and the safer Unreal direction. Mark the status of any Experimental or Beta feature you rely on. Separate verified facts from inferences.

When implementing, make the smallest coherent change, add or update tests for observable behavior, and record the exact build and test commands with their results. State which checks were not run.
