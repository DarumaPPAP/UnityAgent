# C# Anti-pattern Rules

## Correctness and contracts

- CS-API-001: Public API or serialized contract changed without compatibility plan.
- CS-NULL-001: Nullable or collection return contract is ambiguous.
- CS-EX-001: Empty/swallowed catch or exception used as ordinary control flow.
- CS-EX-002: `throw ex;` destroys the original stack trace.
- CS-ASYNC-001: Public `async void` outside event/Unity callback.
- CS-ASYNC-002: `.Result`, `.Wait()` or `.GetAwaiter().GetResult()` blocks normal flow.

## Unity runtime

- CS-UNITY-001: `Update` or per-frame callback does work whose frequency can be reduced.
- CS-UNITY-002: Repeated `GetComponent`, `Find`, `Camera.main` or hierarchy search in a hot path.
- CS-UNITY-003: `Renderer.material` creates unintended material instances.
- CS-UNITY-004: Editor behavior is treated as Player/IL2CPP proof.

## Allocation and performance

- CS-PERF-001: LINQ, closure, iterator, array, collection or string allocation in a measured hot path.
- CS-PERF-002: Boxing through interface/object/enum/params usage in a hot path.
- CS-PERF-003: Repeated enumeration or avoidable collection copying.
- CS-PERF-004: Expensive log argument construction when logging is disabled or filtered.

## Structs

- CS-STRUCT-001: Mutable struct with unclear identity/value semantics.
- CS-STRUCT-002: Large struct copied repeatedly or passed through interfaces/object.
- CS-STRUCT-003: Struct default value is invalid or surprising.
- CS-STRUCT-004: Defensive copies caused by readonly/interface/property access.

A struct is not automatically a problem. Evaluate value semantics, size, immutability, default validity, copying, boxing and Burst/Jobs constraints.

## AOT, reflection and jobs

- CS-AOT-001: Reflection/dynamic/runtime generic construction without IL2CPP stripping plan.
- CS-JOB-001: Managed object/array/string enters Burst or Job code.
- CS-JOB-002: NativeContainer ownership or dependency completion is unclear.
- CS-JOB-003: Job is completed too early, destroying parallelism, or too late, risking correctness.

## Design

- CS-DESIGN-001: Mutable static state, static event, Singleton or Service Locator introduces hidden lifetime.
- CS-DESIGN-002: Manager/Controller/Util/Common/Helper has no precise responsibility.
- CS-DESIGN-003: Unrequested abstraction, cache, pool, fallback or debug system increases complexity.

Each finding must include severity, confidence, affected path, conditions, safe-fix level and required evidence.
