# Graph Observatory Phase 0 Baseline Tests

These tests capture the known Phase 8 foundation gaps without changing the
Graph Observatory implementation. They intentionally fail against the current
baseline and should become passing only when a later approved phase repairs
the corresponding contract.

Run them with:

```text
python -m unittest discover -s Tests/GraphObservatory -p "test_*.py"
```

The tests are not connected to `Tools/validate_all.py` in Phase 0. This keeps
the current contract baseline separate from the deliberately failing repair
cases.
