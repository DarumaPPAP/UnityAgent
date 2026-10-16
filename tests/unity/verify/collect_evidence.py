"""G1/G2/G3を別Gateとして収集する。Fixture/MockをProduction成功へ昇格しない。"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

GATES = ('production_runtime', 'blender_mcp', 'artifact_integrity', 'unity_compile',
         'import_prefab_scene_guid', 'render_capture', 'visual_acceptance',
         'rollback', 'lease_conflict', 'video_decode', 'hot_reload_comparison', 'g2', 'g3')


G1_GATES = GATES[:9]  # G2/G3/video/hot-reload are independently reported, not G1 blockers.

def collect(directory, *, source_revision, artifact_hash):
    directory = Path(directory)
    results = {}
    for gate in GATES:
        path = directory / (gate + '.json')
        result = {'status': 'BLOCKED_NOT_RUN', 'reason': 'Required observation not available'}
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
                if value.get('gate') != gate or value.get('source_revision') != source_revision:
                    raise ValueError('Gate identity or source revision mismatch')
                if value.get('source_sha256') != artifact_hash:
                    raise ValueError('Artifact revision mismatch')
                if value.get('status') == 'passed':
                    if value.get('limitation') or value.get('evidence_level') != 'production_runtime':
                        raise ValueError('Fixture or unverified evidence cannot satisfy Production Gate')
                    refs = value.get('raw_refs')
                    if not isinstance(refs, dict) or not refs:
                        raise ValueError('No raw observation files')
                    for name, expected in refs.items():
                        source = (directory / name).resolve(strict=True)
                        if not source.is_relative_to(directory.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                            raise ValueError('Observation path or hash mismatch')
                    result = {**value, 'status': 'passed'}
                elif value.get('status') == 'failed':
                    result = value
                else:
                    result = {**value, 'status': 'BLOCKED_NOT_RUN'}
            except (ValueError, OSError, TypeError) as exc:
                result = {'status': 'failed', 'reason': str(exc)}
        results[gate] = result
    return {'schema_version': '1.0', 'source_revision': source_revision, 'artifact_hash': artifact_hash,
            'status': 'verified' if all(results[gate]['status'] == 'passed' for gate in G1_GATES) else 'blocked',
            'gates': results, 'token_usage': 'unmeasured', 'latency_comparison': 'unmeasured'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--artifact-hash', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.directory, source_revision=args.source_revision, artifact_hash=args.artifact_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': result['status'], 'gates': {k:v['status'] for k,v in result['gates'].items()}}))
    return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
