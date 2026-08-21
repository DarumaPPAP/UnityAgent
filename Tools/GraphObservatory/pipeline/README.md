# Graph Artifact Pipeline

## Flow

```
Canonical Data
      ↓
Projection Layer
      ↓
Graph Artifact
      ↓
Validation Gate
      ↓
Visualizer Input
```

Invalid graph artifacts must not reach the visualization layer.

Graph remains a derived projection. Canonical YAML and manifests are the source of truth.
