#!/usr/bin/env python3
"""Structural validation only: never publishes Editor PASS evidence."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]

def validate(root=ROOT):
    config = json.loads((root / 'ci/unity-matrix.yaml').read_text())
    errors, guids = [], set()
    if config.get('observation') != 'not_observed':
        errors.append('Fixture inventory must not claim observed Editor evidence')
    for row in config['fixtures']:
        project = root / row['project']
        try:
            version = (project / 'ProjectSettings/ProjectVersion.txt').read_text()
            if 'm_EditorVersion: ' + row['editor'] not in version:
                errors.append(row['id'] + ': exact project Editor version mismatch')
            manifest = json.loads((project / 'Packages/manifest.json').read_text())
            for package, value in manifest['dependencies'].items():
                if value.startswith('file:'):
                    path = (project / 'Packages' / value[5:]).resolve()
                    if not path.is_dir() or not (path / 'package.json').is_file():
                        errors.append(row['id'] + ': local package missing: ' + package)
            if row['id'] == 'canonical-full':
                continue  # Canonical scene/test contents are preserved by the path migration.
            if not list((project / 'Assets').rglob('*.cs')) or not list((project / 'Assets').rglob('*.asmdef')):
                errors.append(row['id'] + ': test implementation/assembly missing')
            for asset in (project / 'Assets').rglob('*'):
                if asset.suffix == '.meta':
                    continue
                meta = Path(str(asset) + '.meta')
                if not meta.exists():
                    errors.append(row['id'] + ': asset .meta missing: ' + asset.name)
                    continue
                match = re.search(r'^guid: ([a-f0-9]{32})$', meta.read_text(), re.MULTILINE)
                if not match or match[1] in guids:
                    errors.append(row['id'] + ': malformed or duplicate GUID: ' + asset.name)
                elif match:
                    guids.add(match[1])
            if row['scope'] == 'scene-native-api-smoke':
                scene = (project / 'Assets/Scenes/PipelineSmoke.unity').read_text()
                for name in ('Main Camera', 'Key Light', 'FovSubject'):
                    if 'm_Name: ' + name not in scene:
                        errors.append(row['id'] + ': scene missing ' + name)
                if row['pipeline'] != 'builtin' and 'srp_package' not in row:
                    errors.append(row['id'] + ': SRP selection policy missing')
        except (OSError, ValueError) as error:
            errors.append(row['id'] + ': ' + str(error))
    return errors

if __name__ == '__main__':
    errors = validate()
    for error in errors:
        print(error, file=sys.stderr)
    print('Unity fixture structure: ' + ('FAIL' if errors else 'PASS (static only)'))
    sys.exit(bool(errors))
