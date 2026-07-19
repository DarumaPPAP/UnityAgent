# Shader Review Gate

## Gate 0: Environment

Unity, pipeline, Graphics API, target device, build type, resolution, MSAA, TAA/STP/upscaler, screen coverage and stage are recorded. Unknown values reduce confidence.

## Gate 1: Correctness

Compile, material properties, keywords, pass/LightMode, render state, SRP Batcher, motion vectors, depth, temporal stability and target Player are valid.

## Gate 2: Static audit

Review fragment-invariant work, duplicate samples/normalize, transcendental functions, divergent branches, long-lived temporaries, local arrays, loops/unroll, precision, interpolators, transparent overdraw, alpha test, SV_Depth, full-screen passes and variants.

## Gate 3: Compiler/GPU

Where available, inspect generated code, register count, spills, occupancy, instruction and texture counts, cache/bandwidth, wave utilization, overdraw and GPU time.

## Gate 4: Before/After

Use fixed camera, scene, resolution and quality; warm up; collect multiple samples; exclude CPU-bound conditions; compare image and temporal behavior; record revert conditions.
