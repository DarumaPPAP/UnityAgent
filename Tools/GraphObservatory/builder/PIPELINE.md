# Graph Artifact Pipeline

## Principle

YAML contracts are the source of truth.

Graph artifacts are derived views only.

```
Canonical YAML
    ↓
Readers
    ↓
Node Generator
    ↓
Edge Resolver
    ↓
Graph Validator
    ↓
Artifacts/graph/*.json
```

## Outputs

- architecture.json
- execution.json
- regression.json
- observatory.json

## Constraints

- Visualizer must never mutate canonical YAML.
- Missing relations must fail validation instead of being guessed.
- Provenance should be preserved during projection.
