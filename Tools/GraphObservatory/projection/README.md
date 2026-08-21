# Phase 8.7 Real Data Projection Layer

## Purpose

Convert UnityAgent canonical runtime data into Graph Observatory projections.

Source of Truth:

```text
.ai YAML / Context Manifest
        ↓
Projection Layer
        ↓
Graph Artifact
        ↓
Visualizer
```

This layer is read-only. It must not modify canonical configuration.

## Projection Targets

- Context Graph
- Harness Graph
- Execution Graph
- Regression Graph

## Projection Pipeline

```text
Canonical Data
        ↓
Projection Runner
        ↓
Context Projection
Harness Projection
Execution Projection
Regression Projection
        ↓
Graph Artifact
        ↓
Validator
```

## Rules

- Preserve provenance.
- Preserve node IDs.
- Preserve typed edges.
- Missing information becomes unresolved, never guessed.
- Graph output is a derived view, not a source of truth.
- Graph editing must not mutate canonical YAML.

## Output

Generated artifacts are consumed by Graph Observatory views:

- Architecture View
- Task View
- Execution Trace View
- Regression View
