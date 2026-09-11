---
name: unity-fix-errors
description: Use when a Unity compile, RenderGraph, Shader, Variant, Player, or target-device failure must be diagnosed and minimally fixed from the first causal error. Produces root cause, bounded change, compatibility impact, and validation evidence. Does not hide failures by weakening Strict Variant, deleting required passes, or claiming unobserved target success.
---

# Unity Fix Errors

- Reproduce and identify the first causal error, not downstream noise.
- Preserve API, serialization, Shader and rendering contracts unless explicitly approved.
- Do not hide Variant errors by collecting everything into SVC or disabling Strict Variant.
- Do not invent include functions or delete MotionVectors/Depth just to compile.
- Do not work around RenderGraph errors with unnecessary copy passes before checking resource declarations, formats and sample counts.
- Distinguish Editor-only success from Player/IL2CPP/target-device success.
- After the minimal fix, report cause, change, compatibility impact and required validation.

## Output contract

- First causal error and reproduction context
- Root-cause explanation with supporting evidence
- Changed files and minimal fix
- Preserved or intentionally changed compatibility contracts
- Validation performed by layer: static / compile / Editor / Player / target device
- Remaining unknowns, risk, and revert condition

## Checklist

- [ ] The first causal error is separated from downstream noise
- [ ] The fix is scoped to the confirmed cause
- [ ] API, serialization, Shader properties, keywords, passes, and RenderState are preserved unless approved
- [ ] RenderGraph resources, formats, sample counts, and lifetime are checked before adding copy work
- [ ] Strict Variant is not weakened to hide a missing variant
- [ ] Editor success is not promoted to Player or target-device success
- [ ] Missing validation is reported as unavailable or unverified, not PASS

## Common mistakes

- Fixing the last visible Console error while leaving the first causal error intact.
- Disabling Strict Shader Variant Matching or stuffing all variants into an SVC to hide a contract mismatch.
- Removing MotionVectors, Depth, or another required pass only to make the Shader compile.
- Adding a RenderGraph copy pass before checking resource declarations and MSAA/format compatibility.
- Inventing an include symbol or API that is not present in the installed Unity/URP version.
- Treating Editor rendering as evidence that IL2CPP, console, or target-device rendering passed.
