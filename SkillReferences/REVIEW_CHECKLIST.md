# Unity Review Checklist

## Context

- [ ] Unity version / package versions
- [ ] Render pipeline / Graphics API / target platform
- [ ] Editor vs Player / Mono vs IL2CPP / build type
- [ ] Burst / Jobs / Entities
- [ ] hot-path frequency and workload
- [ ] public API / serialization / prefab / scene / save-data contracts

## C#

- [ ] semantics, ownership and lifetime
- [ ] nullability and collection contracts
- [ ] async/exception behavior
- [ ] IL2CPP/AOT/stripping
- [ ] Burst/Job managed-data and dependencies
- [ ] hot-path allocations, boxing, closures and repeated lookup
- [ ] struct value semantics, copies and default validity
- [ ] no hidden mutable static lifetime

## Rendering / Shader

- [ ] pass inputs, outputs, timing and resource lifetime
- [ ] Shader external contracts preserved
- [ ] SRP Batcher / `UnityPerMaterial`
- [ ] depth, motion vectors and temporal stability
- [ ] overdraw, bandwidth, register pressure and synchronization
- [ ] variant reduction separated from missing-variant prevention
- [ ] target Player validation

## Evidence

- [ ] static findings separated from Evidence Required
- [ ] Before/After conditions fixed
- [ ] multiple samples and warm-up
- [ ] CPU/GPU bound confirmed
- [ ] image/temporal comparison
- [ ] revert condition recorded
- [ ] unverified claims stated explicitly
