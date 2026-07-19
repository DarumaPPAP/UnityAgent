# Shader Refactor Policy

## External contract

List and preserve Shader name, properties, keywords, passes, LightModes, render states, queue/type, CBUFFER, textures/samplers, script property IDs, include APIs and Shader Graph custom-function signatures.

## Relatively safe

- reuse identical sample results
- remove duplicate or dead computation
- narrow variable scope
- simplify constant expressions
- share identical expressions
- compile-time exclude debug paths

## Measurement required

- branch changes
- precision reduction
- normalize removal
- vertex-stage migration
- LUT conversion
- unroll changes
- pass integration
- render-target format changes
- downscaling

## High risk

- Blend/ZWrite/ZTest/Queue changes
- MotionVector/Depth/Temporal changes
- variant stripping
- CBUFFER layout changes
- alpha-test changes
- shader reassignment

One commit or patch must test one primary hypothesis. Revert when GPU improvement is within noise, image/temporal quality regresses, compatibility breaks or another stage becomes worse.
