# Phase 8: UnityAgent Graph Observatory

## Goal

Create an observability layer for UnityAgent. The goal is not only to display graphs, but to understand why an Agent decision was made.

## Core Views

- Architecture View
- Task Explorer
- Execution Trace
- Regression Dashboard

## Design Principles

- Graph data is generated from canonical YAML sources.
- Visualizer never edits policy or harness contracts directly.
- Every node keeps provenance information.
- Detail panels are more important than raw graph canvas.

## Pipeline

```
.ai/*.yaml
    |
    v
Graph Builder
    |
    v
graph.json
    |
    v
Graph Observatory UI
```

## Phase 8 Milestones

1. Graph Export Pipeline
2. Overview Graph
3. Task Explorer
4. Execution Timeline
5. Regression Dashboard
6. Diff and Provenance View
