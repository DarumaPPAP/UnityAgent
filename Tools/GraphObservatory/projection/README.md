# Phase 8.7 Real Data Projection Layer

## Purpose

Convert UnityAgent canonical runtime data into Graph Observatory projections.

Source of Truth:

```
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

## Rules

- Preserve provenance.
- Preserve node IDs.
- Preserve typed edges.
- Missing information becomes unresolved, never guessed.
