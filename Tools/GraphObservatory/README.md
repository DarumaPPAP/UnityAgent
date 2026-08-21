# UnityAgent Context Explorer

This directory contains the read-only Context Explorer projection. Canonical
Policy, Context Pack, Harness, and Regression files remain the source of truth.

## Build and validate

```text
python Tools/GraphObservatory/build.py --view context --check
python Tools/GraphObservatory/build.py --view context --bundle Artifacts/GraphObservatory/ContextExplorer
```

The bundle is static and offline. It has no edit, save, apply, agent-control,
or Canonical YAML write surface. The MVP shows Context metadata and explicit
one-hop relations only.

Legacy builder and projection entry points remain as thin compatibility
adapters until a later approved cleanup removes them.
