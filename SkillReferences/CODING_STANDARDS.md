# Unity C# Coding Standards

## Context first

Before review or implementation, resolve Unity version, render pipeline, target platform, Editor/Player, Mono/IL2CPP, Development/Release, Burst/Jobs/Entities, hot-path frequency, public API and serialization compatibility.

## Naming

- Namespace: `<RootNamespace>.<FeatureName>`
- private field: `_camelCase`
- public API/type/member: `PascalCase`
- enum type: `E_UPPER_SNAKE_CASE`
- struct type: `S_UPPER_SNAKE_CASE`
- const: `SCREAMING_SNAKE_CASE`
- custom struct: prefer `readonly struct` when semantics allow

## Design

- Prefer explicit ownership and lifetime.
- Do not add mutable static state, static events, Singleton or Service Locator.
- Do not create `Manager`, `Controller`, `Util`, `Common`, `Helper` without a precise responsibility.
- Do not add Profile/Controller/Platform abstraction unless the specification requires it.
- Do not change public API, serialized names/types, enum values, save formats or file names without compatibility analysis.

## Runtime safety

- Do not add public `async void` except event or Unity callbacks.
- Do not use `Task.Result`, `.Wait()` or `.GetAwaiter().GetResult()` as normal flow.
- Use `throw;`, not `throw ex;`.
- Do not swallow exceptions or use exceptions as ordinary control flow.
- `BinaryFormatter` is prohibited.
- Reflection, `dynamic`, `Activator`, `MethodInfo.Invoke` and runtime generic construction require IL2CPP/AOT/stripping review.

## Performance

- Do not declare a pattern slow without frequency and evidence.
- In hot paths, review LINQ, closures, arrays, collections, strings, boxing, `params object[]`, logging, repeated enumeration and `Renderer.material`.
- Do not state that structs are generally bad. Evaluate identity, copy semantics, size, immutability, default validity, boxing and defensive copies.
- For Burst/Jobs, require unmanaged/blittable data and explicit NativeContainer ownership/dependency completion.
- Editor success is not Player/IL2CPP proof.

## Shader boundary

ShaderLab/HLSL/Compute/RendererFeature/RenderGraph work must use `SkillReferences/SHADER_PERFORMANCE_STANDARDS.md` and the dedicated Shader Agents. C# rules cover script-side property IDs, keywords, pass/kernel names, buffers and material contracts, but do not replace GPU performance analysis.
