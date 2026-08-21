# Graph Observatory Builder

Phase 8 foundation for converting canonical UnityAgent contracts into derived graph artifacts.

## Flow

```
.ai YAML / Manifest / Golden Data
          ↓
   Graph Builder
          ↓
 Artifacts/graph/*.json
          ↓
 Graph Observatory UI
```

## Rules

- Graph output is a derived view.
- Canonical YAML remains the source of truth.
- Provenance should be preserved on nodes and edges.
- Visualization must not mutate contracts directly.
