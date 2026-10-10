#!/usr/bin/env python3
"""Prove a wheel works in an isolated venv outside the source checkout."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv

PROOF = r'''
import hashlib, json
from unityagent.resources import resource_root
from unityagent.cli import _fingerprint
from unityagent.policy.security.capability_policy import policy_for_capability
from unityagent.runtime.tooling.provider_contract import load_provider_registry
from unityagent.runtime.reference_implementation.profiles import CATALOG
from unityagent.context.assembly.materialize_context import materialize_context
from unityagent.context.manifest.build_context_manifest import build
from unityagent.runtime.contracts.reasoning_output import require_reasoning_output_contract
root = resource_root()
manifest = json.loads((root / 'resource-manifest.json').read_text())
for relative, expected in manifest.items():
    assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
assert not any(value.startswith('missing:') for value in _fingerprint().values())
assert policy_for_capability('project.inspect')['operation_kind'] == 'read'
assert load_provider_registry().providers
assert CATALOG.get('artist_subagent').profile_id == 'artist_subagent'
import importlib
for profile_id in CATALOG.to_mapping()['profiles']:
    importlib.import_module(CATALOG.definition(profile_id).session_entrypoint)
for route in ('generic-planning', 'csharp-local-fix', 'rendering-incident', 'world-creation', 'artist-lookdev'):
    view = materialize_context('wheel-' + route, route)
    assert view['selected_refs']['primary_skill']['revision'].startswith('sha256:')
assert build('wheel-manifest', 'csharp-local-fix')['materialized_context']['route_id'] == 'csharp-local-fix'
for profile_id in ('graphics_subagent', 'performance_subagent', 'world_creator_subagent'):
    execution = CATALOG.get(profile_id).execution
    assert (root / execution['instructions_ref']).is_file()
    assert (root / execution['output_contract_ref']).is_file()
    require_reasoning_output_contract(execution['output_contract_ref'])
print(json.dumps({'status':'passed','resource_count':len(manifest),'fingerprint':_fingerprint()}))
'''

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--dependency-dir', type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='unityagent-wheel-proof-') as temporary:
        work = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(work / 'venv')
        executable_dir = work / 'venv' / ('Scripts' if os.name == 'nt' else 'bin')
        python = executable_dir / ('python.exe' if os.name == 'nt' else 'python')
        cli = executable_dir / ('unity-agent.exe' if os.name == 'nt' else 'unity-agent')
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        install = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check']
        if args.dependency_dir:
            install.extend(['--no-index', '--find-links', str(args.dependency_dir.resolve())])
        subprocess.run([*install, str(wheel)], cwd=work, env=env, check=True)
        subprocess.run([str(cli), '--help'], cwd=work, env=env, check=True)
        subprocess.run([str(python), '-c', PROOF], cwd=work, env=env, check=True)
        project = work / 'project'
        for folder in ('Assets', 'Packages', 'ProjectSettings'):
            (project / folder).mkdir(parents=True)
        (project / 'Packages/manifest.json').write_text('{"dependencies":{}}', encoding='utf-8')
        (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.6.0f1\n', encoding='utf-8')
        subprocess.run([str(cli), 'doctor', '--project-path', str(project), '--state-root', str(work/'state')], cwd=work, env=env, check=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
