"""固定Source Lockから、移行中に許可された配布パスだけを解決する。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def resolve_source_paths(lock: dict) -> dict[str, str]:
    hub = lock['hub']
    artist = lock['specialist_sources']['artist_subagent']
    if hub.get('repository') != 'DarumaPPAP/UnitySubAgentHub' or re.fullmatch(r'[0-9a-f]{40}', hub.get('commit', '')) is None:
        raise ValueError('Hub source must have the canonical repository and immutable full SHA')
    layouts = {
        'Tests/Hub/export_agent_snapshot.py': ('Registry/subagents.yaml', 'SubAgents/artist_subagent/manifest.yaml', 'Tests/Hub/validate_registry.py', 'Tests/Hub'),
        'Hub/Tools/export_snapshot.py': ('Hub/Registry/subagents.yaml', 'Hub/SubAgents/artist_subagent/manifest.yaml', 'Hub/Tools/validate_registry.py', 'Hub/Tests'),
    }
    exporter = hub.get('snapshot_exporter')
    if exporter not in layouts:
        raise ValueError('Unknown snapshot exporter')
    registry, manifest, validator, tests = layouts[exporter]
    if hub.get('registry') != registry or artist.get('manifest') != manifest or artist.get('backend_package') != 'Packages/com.darumappap.artist-subagent':
        raise ValueError('Source Lock catalog layout or package identity is inconsistent')
    cli = artist.get('backend_cli_project')
    if cli not in ('src/UnityArtist.Cli/UnityArtist.Cli.csproj', 'cli/artist/UnityArtist.Cli.csproj'):
        raise ValueError('Unknown Artist CLI project')
    moved_cli = cli == 'cli/artist/UnityArtist.Cli.csproj'
    return {'repository': hub['repository'], 'commit': hub['commit'], 'hub_exporter': exporter, 'hub_registry': registry, 'hub_validator': validator, 'hub_tests': tests, 'artist_cli_project': cli, 'artist_contract_verifier': 'ci/verify/verify_artist_backend_contract.py' if moved_cli else 'Tests/Backend/verify_artist_backend_contract.py', 'unity_api_verifier': 'ci/verify/verify-unity-api-compatibility.py' if moved_cli else 'Tests/Compatibility/verify-unity-api-compatibility.py'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'src/unityagent/runtime/distribution/subagent-sources.lock.json')
    args = parser.parse_args()
    for key, value in resolve_source_paths(json.loads(args.lock.read_text(encoding='utf-8'))).items():
        print(f'{key}={value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
