# Python src migration (P5 and Agent-owned P6)

The host product is the `unityagent-control-plane` distribution, with the unchanged
`unity-agent` executable and version `0.0.8-beta` (`0.0.8b0` in Python metadata).
Implementation modules are under `src/unityagent` in lower-case snake_case packages.
Repository validation, including the former Policy/Context validators and loop
validation script, lives in `tools`, evaluation in `eval`, and tests in
`tests/<domain>`. The exact 551-file before/after inventory is
[python-src-path-map.json](python-src-path-map.json).

| Previous owner | Current owner |
| --- | --- |
| Context, ControlPlane, Operations, Orchestration, Persistence, Policy, Runtime | src/unityagent/context, control_plane, operations, orchestration, persistence, policy, runtime |
| Tools/unity_agent_cli.py | src/unityagent/cli.py |
| Other Tools | tools (subdirectories use snake_case) |
| Eval | eval |
| Layer Tests and root Tests | tests/domain |
| Specs machine contracts | src/unityagent/contracts |
| Specs human documentation | docs/architecture/specifications |
| SkillReferences shared authored standards | docs/standards |
| Templates | docs/templates |
| Prompt duplicate templates | src/unityagent/context/prompt/templates |

The four Prompt files were byte-identical to their corresponding Context templates
at the migration baseline. Active references now target Context templates before the
redundant root copies are removed. Standards remain authored once in docs/standards;
Skills continue to point to them. Existing `.agents` authored Skills and Plugin paths
remain unchanged.

## Resources and identities

Ruling: package a generated, exact resource view instead of detecting a checkout at
runtime. `setup.py` copies runtime YAML/JSON/Markdown/text/C# resources, authored
Skills/plugin metadata, shared standards/templates/human specifications, VERSION and
the evaluation fingerprint contract into `unityagent/_resources`. Each copied file
has its canonical repository-relative path and SHA-256 in resource-manifest.json.
This is generated build output, ignored in source control, and excluded from the
sdist; the wheel build reconstructs it from the authored sources. This avoids a
second authored source and prevents arbitrary checkout siblings from overriding
packaged policies. A stale build must be rebuilt; editable installation and the
canonical validation entry refresh this view explicitly.

Ruling: Python module names and physical resource paths migrate, while profile,
provider, capability, authority, evidence producer and policy leaf-clause IDs remain
unchanged. Exact output-contract allowlists, strict regexes and confinement checks
migrate together. New source paths intentionally change definition/context hashes;
historical approvals and durable evidence are not rewritten. The external Hub source
lock is relocated byte-for-byte; its pin and Hub contract paths are reconciled in the
separate P3/P4 consumer change.

Ruling: repository validators audit authored source. Capability foundation receives
`--root` from tools/validate_all.py and loads the catalog from that same root;
otherwise an installed resource snapshot could hide a later authored mutation.
A regression test changes only a temporary catalog and requires a validation finding.
The normal Context import path replaces filesystem loading of Python modules.

Ruling: managed Windows deployment remains `%LOCALAPPDATA%/UnityAgent/ControlPlane`.
UPM executable resolution, installer names, GUID/meta bytes, package IDs and version
mirrors stay unchanged. The specialist module entrypoint uses the installed lower-case
namespace, with its sanitized Python path anchored at the package's parent. The
exported reference GoldenTaskRunner uses the established host state directory for its
default persistence location, so installed package data is never a write target.

The legacy `myunitymcp` observation field remains because live consumers still use it.
No MyUnityMCP adapter, legacy port, auto-install, or new backend layer is introduced.
P0 inventory/plans and the execution Goal retain their historical path citations.
Layout enforcement is deferred to P8, independently of the authority map.

## Validation and remaining environment boundaries

The original canonical inventory retains 28 validators, 8 YAML roots, the graph
projection check and all 10 original test suites. Packaging and the nested reference
implementation suite are added. An isolated installed-wheel proof checks `--help`,
`doctor`, every copied resource hash, complete definition fingerprints, policy,
provider/catalog loaders, five Context routes, Context Manifest, specialist module
imports and three reasoning instruction/output-schema bindings. The proof runs in a
fresh venv from a temporary cwd with PYTHONPATH removed; it is a CI step with the
existing Canonical Validation job name.

Development reproduction:

```sh
python -m pip install -e . build
python tools/validate_all.py
python -m unittest discover -s .github/ProductionSmoke -p 'test_*.py'
python -m unittest discover -s tests -p 'test_*.py'
python -m build
python tools/verify_installed_wheel.py --wheel dist/unityagent_control_plane-0.0.8b0-py3-none-any.whl
npm pack ./Packages/com.darumappap.unity-agent
```

Host results are recorded in repository-consolidation-progress.md. Doctor reports
unavailable Unity/Artist binaries as unavailable; their absence is not converted into
Editor success. Windows process/PowerShell and actual Unity Editor/Player/Visual gates
require their execution environments and remain BLOCKED_NOT_RUN locally. No release,
tag, push, PR or merge is performed by this implementation worktree.
