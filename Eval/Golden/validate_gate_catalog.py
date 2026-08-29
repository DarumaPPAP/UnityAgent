#!/usr/bin/env python3
"""Validate that every Task Contract Quality Gate exists in the canonical gate catalog."""

from __future__ import annotations

from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / '.ai' / 'context-index.yaml'
QUALITY_PATH = ROOT / '.ai' / 'harness' / 'quality-gates.yaml'


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(data, dict):
        raise ValueError(f'Expected mapping: {path}')
    return data


def main() -> int:
    errors: list[str] = []
    try:
        index = load_yaml(INDEX_PATH)
        quality = load_yaml(QUALITY_PATH)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f'Gate Catalog validation failed:\n- {exc}')
        return 1

    known = set((quality.get('gates', {}) or {}).keys())
    referenced: set[str] = set()
    for route_key, route in (index.get('routes', {}) or {}).items():
        if not isinstance(route, dict) or not route.get('task_contract'):
            continue
        try:
            contract = load_yaml(ROOT / str(route['task_contract']))
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{route_key}: failed to load Task Contract: {exc}')
            continue
        for field in ('required_quality_gates', 'conditional_quality_gates'):
            for gate in contract.get(field, []) or []:
                gate_id = str(gate)
                referenced.add(gate_id)
                if gate_id not in known:
                    errors.append(f"{route.get('id', route_key)}: undefined Quality Gate {gate_id}")

    if errors:
        print('Gate Catalog validation failed:')
        for error in errors:
            print(f'- {error}')
        return 1

    print(f'Gate Catalog validation passed: {len(referenced)} referenced gates / {len(known)} catalog gates.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
