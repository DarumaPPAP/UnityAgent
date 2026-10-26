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
    expected_artist = {'source_mode': 'same_checkout', 'repository': 'DarumaPPAP/UnityAgent', 'manifest': 'subagent/artist_subagent/manifest.yaml', 'backend_package': 'subagent/artist_subagent/tools/editor', 'backend_provider': 'unity_cli'}
    if artist != expected_artist:
        raise ValueError('Artist execution sources must belong to the same UnityAgent checkout and Unity CLI')
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
    if hub.get('registry') != registry:
        raise ValueError('Source Lock catalog layout or package identity is inconsistent')
    return {'repository': artist['repository'], 'source_mode': artist['source_mode'], 'artist_manifest': artist['manifest'], 'artist_package': artist['backend_package'], 'artist_provider': artist['backend_provider'], 'historical_hub_repository': hub['repository'], 'historical_hub_commit': hub['commit'], 'hub_exporter': exporter, 'hub_registry': registry, 'hub_validator': validator, 'hub_tests': tests}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'src/unityagent/runtime/distribution/subagent-sources.lock.json')
    args = parser.parse_args()
    for key, value in resolve_source_paths(json.loads(args.lock.read_text(encoding='utf-8'))).items():
        print(f'{key}={value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
