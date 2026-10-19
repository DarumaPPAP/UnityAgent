#!/usr/bin/env python3
"""Direct-Editor CI; host success never implies Editor evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / 'tests/unity/matrix.yaml'  # JSON is a YAML 1.2 subset.

def find_editor(version, editor=None, editor_root=None, system=None):
    """Select only the exact installation; a broken explicit override fails closed."""
    system = system or platform.system()
    if system not in {'Windows', 'Linux'}:
        raise RuntimeError('Supported Unity CI hosts are Windows and Linux; observed: ' + system)
    direct = editor or os.getenv('UNITY_EDITOR')
    configured_root = editor_root or os.getenv('UNITY_EDITOR_ROOT')
    name = 'Unity.exe' if system == 'Windows' else 'Unity'
    if direct:
        candidates = [Path(direct).expanduser()]
    else:
        if configured_root:
            roots = [Path(configured_root).expanduser()]
        elif system == 'Windows':
            roots = [Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Unity/Hub/Editor']
        else:
            roots = [Path('/opt/unity'), Path.home() / 'Unity/Hub/Editor']
        candidates = [root / version / 'Editor' / name for root in roots]
    for candidate in candidates:
        if candidate.is_file() and (system == 'Windows' or os.access(candidate, os.X_OK)):
            return candidate.resolve()
    raise RuntimeError('Exact executable Editor unavailable; configure --editor / UNITY_EDITOR or '
                       '--editor-root / UNITY_EDITOR_ROOT. Checked: ' + ', '.join(map(str, candidates)))

def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)

def select_release(payload, baseline):
    candidates = []
    for item in payload.get('results', []):
        match = re.fullmatch(r'(6000)\.(\d+)\.(\d+)([ab])(\d+)', item.get('version', ''))
        if not match or int(match[2]) <= int(baseline.split('.')[1]):
            continue
        for download in item.get('downloads', []):
            url = download.get('url', '')
            parsed = urllib.parse.urlparse(url)
            if (download.get('platform') == 'LINUX' and download.get('architecture') == 'X86_64'
                    and download.get('type') == 'TAR_XZ' and parsed.scheme == 'https'
                    and parsed.hostname in {'download.unity3d.com', 'beta.unity3d.com'}
                    and re.fullmatch(r'[a-fA-F0-9]+', item.get('shortRevision', ''))):
                candidates.append(((int(match[2]), int(match[3]), match[4], int(match[5])),
                                   dict(version=item['version'], changeset=item['shortRevision'], editor_url=url)))
    if not candidates:
        raise ValueError('No next-stream prerelease Linux Editor in official archive response')
    return max(candidates, key=lambda pair: pair[0])[1]

def resolve_release(baseline):
    # Iterate all pages: API order is release date, not semantic version order.
    results, offset = [], 0
    while True:
        query = urllib.parse.urlencode({'version': '6000', 'limit': 100, 'offset': offset,
                                       'order': 'RELEASE_DATE_DESC'})
        page = fetch('https://services.api.unity.com/unity/editor/release/v1/releases?' + query)
        rows = page.get('results', [])
        results.extend(rows)
        offset += len(rows)
        if not rows or offset >= page.get('total', offset):
            break
        if offset > 10000:
            raise ValueError('Archive pagination exceeded safety bound')
    return select_release({'results': results}, baseline)

def package_version(payload, editor):
    editor_pair = tuple(map(int, editor.split('.')[:2]))
    candidates = []
    for version, info in payload.get('versions', {}).items():
        if not re.fullmatch(r'17\.\d+\.\d+', version):
            continue
        minimum = info.get('unity', '')
        if not re.fullmatch(r'6000\.\d+', minimum):
            continue
        if tuple(map(int, minimum.split('.'))) != editor_pair:
            continue
        # unityRelease is a patch constraint: conservatively reject unknown forms.
        release = info.get('unityRelease', '0f1')
        match = re.fullmatch(r'(\d+)f(\d+)', release)
        current = re.fullmatch(r'6000\.\d+\.(\d+)f(\d+)', editor)
        if not match or not current:
            continue
        if minimum == '.'.join(editor.split('.')[:2]) and tuple(map(int, match.groups())) > tuple(map(int, current.groups())):
            continue
        candidates.append((tuple(map(int, version.split('.'))), version))
    if not candidates:
        raise ValueError('No stable SRP 17 package with compatible official Unity minimum')
    return max(candidates)[1]

def test_evidence(path):
    root = ET.parse(path).getroot()
    if root.tag != 'test-run' or root.get('result') != 'Passed':
        raise ValueError('Test run did not pass')
    cases = root.findall('.//test-case')
    if not cases or any(case.get('result') != 'Passed' for case in cases):
        raise ValueError('Zero, skipped, inconclusive, or failed test cases')
    if int(root.get('total', '-1')) != len(cases) or int(root.get('passed', '-1')) != len(cases):
        raise ValueError('Test totals disagree with passing test cases')
    for key in ('failed', 'skipped', 'inconclusive'):
        if int(root.get(key, '0')) != 0:
            raise ValueError('Nonpassing test count')
    return len(cases)

def stage_artist_tests(package_root, project):
    """Expose the baseline package's unassembled tests only in the disposable copy."""
    source = ROOT / 'tests/unity/editor/artist'
    tests = sorted(source.rglob('*.cs'))
    if not tests:
        raise RuntimeError('Canonical full suite has no Artist Editor test sources')
    if list(source.rglob('*.asmdef')):
        return []  # Existing package assemblies are exposed through manifest.testables.
    destination = project / 'Assets/CiArtistPackageTests'
    destination.mkdir(parents=True, exist_ok=False)
    inventory = []
    for test in tests:
        target = destination / test.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(test, target)
        inventory.append({'source': str(test.relative_to(ROOT)),
                          'sha256': hashlib.sha256(test.read_bytes()).hexdigest()})
    (destination / 'CiArtistPackageTests.asmdef').write_text(json.dumps({
        'name': 'UnityCi.ArtistPackage.Tests', 'references': ['DarumaPPAP.UnityArtist.Editor'],
        'includePlatforms': ['Editor'], 'optionalUnityReferences': ['TestAssemblies']}), encoding='utf-8')
    return inventory

def download_editor(release, target):
    target.mkdir(parents=True, exist_ok=True)
    archive = target / 'editor.tar.xz'
    urllib.request.urlretrieve(release['editor_url'], archive)
    with tarfile.open(archive, 'r:xz') as bundle:
        bundle.extractall(target, filter='data')
    archive.unlink()
    editors = list(target.glob('**/Editor/Unity'))
    if len(editors) != 1:
        raise ValueError('Official archive does not contain one Editor/Unity')
    return editors[0]

def reject_symlinks(path):
    current = Path(path).absolute()
    for candidate in (current, *current.parents):
        if candidate.is_symlink():
            raise ValueError('Symlink input/output path is not permitted: ' + str(candidate))


def confined_source(root, path):
    reject_symlinks(root)
    reject_symlinks(path)
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise ValueError('Input escapes repository: ' + str(path))
    return resolved


def prepare_paths(config, fixture, requested_output):
    """Read-only preflight; reject all overlapping paths before writing anything."""
    source = confined_source(ROOT, ROOT / fixture['project'])
    manifest = json.loads(confined_source(ROOT, source / 'Packages/manifest.json').read_text(encoding='utf-8'))
    local = {}
    protected = []
    for row in config['fixtures']:
        candidate = confined_source(ROOT, ROOT / row['project'])
        protected.append(candidate)
        path = confined_source(ROOT, candidate / 'Packages/manifest.json')
        if path.is_file():
            dependencies = json.loads(path.read_text(encoding='utf-8'))['dependencies']
            for package, value in dependencies.items():
                if value.startswith('file:'):
                    target = confined_source(ROOT, candidate / 'Packages' / value[5:])
                    protected.append(target)
                    if candidate == source:
                        local[package] = target
    requested = Path(requested_output).absolute()
    reject_symlinks(requested)
    output = requested.resolve()
    for path in protected:
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError('Output overlaps protected fixture/package input: ' + str(path))
    # Validate every hashed source and reject symlinks before mkdir/unlink as well.
    inputs = input_hashes(ROOT, source, local, MATRIX)
    return source, manifest, local, output, inputs


def input_hashes(root, source, local_packages, matrix):
    """Deterministic confined source inventory, excluding generated caches."""
    root = Path(root).absolute()
    files = set()
    excluded = {'Library', 'Temp', 'Logs', 'obj', 'bin', '.git', '.cache',
                'node_modules', '__pycache__'}
    def include(path):
        path = confined_source(root, path)
        if path.is_file():
            files.add(path)
    def tree(path):
        path = confined_source(root, path)
        if not path.is_dir():
            return
        for directory, folders, names in os.walk(path, followlinks=False):
            folders[:] = sorted(folder for folder in folders if folder not in excluded)
            for folder in folders:
                confined_source(root, Path(directory) / folder)
            for name in sorted(names):
                include(Path(directory) / name)
    include(matrix)
    tree(source / 'Assets')
    tree(source / 'ProjectSettings')
    include(source / 'Packages/manifest.json')
    include(source / 'Packages/packages-lock.json')
    for package in sorted(local_packages):
        tree(local_packages[package])
    inventory = {path.relative_to(root.resolve()).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(files, key=lambda path: path.relative_to(root.resolve()).as_posix())}
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(algorithm='sha256', digest=digest, files=inventory)


def cleanup_workspace(workspace):
    """Retry only Windows ERROR_DIR_NOT_EMPTY (145); never hide a persistent failure."""
    for attempt in range(4):
        try:
            workspace.cleanup()
            return attempt
        except OSError as error:
            if getattr(error, 'winerror', None) != 145 or attempt == 3:
                raise
            time.sleep(0.25 * (attempt + 1))


def commit_identity():
    supplied = os.getenv('GITHUB_SHA', '')
    if re.fullmatch(r'[a-fA-F0-9]{40,64}', supplied):
        return dict(commit=supplied.lower(), source='GITHUB_SHA')
    try:
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                         text=True, stderr=subprocess.DEVNULL).strip()
        if re.fullmatch(r'[a-fA-F0-9]{40,64}', commit):
            return dict(commit=commit, source='git-rev-parse')
    except (OSError, subprocess.SubprocessError):
        pass
    return dict(commit=None, source='unavailable')


def run(args):
    config = json.loads(confined_source(ROOT, MATRIX).read_text(encoding='utf-8'))
    fixture = next(row for row in config['fixtures'] if row['id'] == args.fixture)
    source, manifest, local_inputs, output, initial_inputs = prepare_paths(config, fixture, args.output)
    output.mkdir(parents=True, exist_ok=True)
    # Never reuse a previous test result as evidence of this execution.
    for name in ('results.xml', 'editor.log', 'editor-version.txt', 'evidence.json',
                 'packages-lock.json', 'manifest.json', 'requested-manifest.json', 'srp-selection.json',
                 'editor.stdout.log', 'editor.stderr.log', 'pipeline-smoke.png', 'graphics-device.json'):
        (output / name).unlink(missing_ok=True)
    evidence = dict(status='BLOCKED_NOT_RUN', observation='not_observed', fixture=fixture['id'],
                    project=fixture['project'], pipeline=fixture['pipeline'],
                    requested_editor=fixture['editor'], packages={}, srp_package=fixture.get('srp_package'),
                    package_policy=config['package_policy'], host_platform=platform.system(),
                    editor_test_process_started=False, run_id=os.getenv('GITHUB_RUN_ID', 'local'),
                    run_attempt=os.getenv('GITHUB_RUN_ATTEMPT', '1'), reason='Editor not run')
    evidence['input_hashes'] = initial_inputs
    evidence['source_identity'] = commit_identity()
    workspace, project = None, None
    code = 2
    try:
        release = resolve_release(config['canonical_editor']) if args.canary else None
        version = release['version'] if release else fixture['editor']
        evidence['requested_editor'] = version
        if release:
            evidence['archive_release'] = release
        evidence['packages'] = manifest['dependencies'].copy()
        (output / 'requested-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if fixture.get('version_provenance'):
            evidence['version_provenance'] = fixture['version_provenance']
        if os.getenv('UNITY_LICENSE_READY') != 'true':
            raise RuntimeError('Prelicensed runner required: set UNITY_LICENSE_READY=true only after licensing')
        if fixture.get('requires_graphics') and os.getenv('UNITY_GRAPHICS_READY') != 'true':
            raise RuntimeError('Graphics smoke requires provisioned GPU/display: UNITY_GRAPHICS_READY=true')
        try:
            editor = find_editor(version, getattr(args, 'editor', None), getattr(args, 'editor_root', None))
        except RuntimeError:
            # P7 archive/download policy is Linux-only. Never extract it on Windows,
            # and never silently replace an explicitly targeted executable.
            if (release and platform.system() == 'Linux'
                    and not (getattr(args, 'editor', None) or os.getenv('UNITY_EDITOR'))
                    and not getattr(args, 'editor_root', None)
                    and os.getenv('UNITY_ALLOW_EDITOR_DOWNLOAD') == 'true'):
                editor = download_editor(release, Path(os.getenv('RUNNER_TEMP') or tempfile.gettempdir())
                                         / ('unity-ci-' + version))
            else:
                raise
        evidence['editor_path'] = str(editor)
        measured = subprocess.run([str(editor), '-version'], capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=60)
        (output / 'editor-version.txt').write_text(measured.stdout + measured.stderr, encoding='utf-8')
        if measured.returncode or not re.search(r'(?<![\w.])' + re.escape(version) + r'(?![\w.])', measured.stdout):
            raise RuntimeError('Installed Editor version does not match requested exact version')
        evidence['observed_editor'] = version
        # Separate workspace copies preserve canonical source and leave no stale results.
        workspace = tempfile.TemporaryDirectory(prefix='unity-ci-owned-', dir=output)
        project = Path(workspace.name) / 'project'
        project.mkdir()
        for directory in ('Assets', 'ProjectSettings'):
            if (source / directory).is_dir():
                shutil.copytree(source / directory, project / directory)
            else:
                (project / directory).mkdir()
        (project / 'Packages').mkdir()
        for name in ('manifest.json', 'packages-lock.json'):
            if (source / 'Packages' / name).is_file():
                shutil.copy2(source / 'Packages' / name, project / 'Packages' / name)
        local_packages = {}
        for package, location in manifest['dependencies'].items():
            if location.startswith('file:'):
                target = local_inputs[package]
                if not target.is_dir():
                    raise RuntimeError('Missing local package: ' + package)
                local_packages[package] = target
                package_metadata = json.loads((target / 'package.json').read_text(encoding='utf-8'))
                if package_metadata.get('name') != package or not package_metadata.get('version'):
                    raise RuntimeError('Local package identity/version missing: ' + package)
                evidence.setdefault('local_package_versions', {})[package] = package_metadata['version']
                manifest['dependencies'][package] = 'file:' + target.as_posix()
        if fixture.get('scope') == 'full':
            artist = 'com.darumappap.artist-subagent'
            if artist not in local_packages:
                raise RuntimeError('Canonical full suite requires local Artist package')
            manifest.setdefault('testables', [])
            if artist not in manifest['testables']:
                manifest['testables'].append(artist)
            evidence['staged_package_tests'] = stage_artist_tests(local_packages[artist], project)
        srp = fixture.get('srp_package')
        if srp:
            metadata = fetch('https://packages.unity.com/' + srp)
            selected = package_version(metadata, version)
            manifest['dependencies'][srp] = selected
            evidence['packages'][srp] = selected
            (output / 'srp-selection.json').write_text(json.dumps({'package': srp, 'version': selected,
                'source': 'https://packages.unity.com/' + srp, 'metadata': metadata['versions'][selected]}, indent=2), encoding='utf-8')
        (project / 'Packages/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: ' + version + '\n', encoding='utf-8')
        results, log = output / 'results.xml', output / 'editor.log'
        command = [str(editor), '-batchmode', '-projectPath', str(project), '-runTests',
                   '-testPlatform', 'EditMode', '-testResults', str(results), '-logFile', str(log)]
        if not fixture.get('requires_graphics'):
            command.insert(2, '-nographics')
        if fixture.get('test_filter'):
            command.extend(['-testFilter', fixture['test_filter']])
        process_env = dict(os.environ, UNITY_CI_ARTIFACTS=str(output))
        with (output / 'editor.stdout.log').open('w', encoding='utf-8') as stdout, (output / 'editor.stderr.log').open('w', encoding='utf-8') as stderr:
            try:
                completed = subprocess.run(command, stdout=stdout, stderr=stderr, env=process_env,
                                           timeout=getattr(args, 'timeout', 3600))
            except subprocess.TimeoutExpired:
                evidence['editor_test_process_started'] = True
                evidence['status'], evidence['observation'] = 'FAIL', 'observed'
                raise
        evidence['editor_test_process_started'] = True
        evidence['status'], evidence['observation'] = 'FAIL', 'observed'
        evidence['editor_exit_code'] = completed.returncode
        diagnostic_logs = ''.join((output / name).read_text(encoding='utf-8-sig', errors='replace')
                                  for name in ('editor.log', 'editor.stdout.log', 'editor.stderr.log')
                                  if (output / name).exists())
        if 'UNITY_CI_GRAPHICS_UNAVAILABLE' in diagnostic_logs:
            evidence['status'], evidence['observation'] = 'BLOCKED_NOT_RUN', 'not_observed'
            raise RuntimeError('Measured Editor graphics device unavailable; see Editor logs')
        if completed.returncode:
            # Unity license faults mean no test execution, not an assertion failure.
            if not results.exists() and re.search(r'(?i)(no valid license|failed to activate|licensing.*(failed|error))', diagnostic_logs):
                evidence['status'] = 'BLOCKED_NOT_RUN'
                evidence['observation'] = 'not_observed'
                raise RuntimeError('Editor licensing unavailable; see editor.log')
            raise ValueError('Editor returned exit code ' + str(completed.returncode))
        evidence['tests_passed'] = test_evidence(results)
        if not log.is_file() or not log.stat().st_size:
            raise ValueError('Editor log missing')
        lock = project / 'Packages/packages-lock.json'
        if not lock.is_file():
            raise ValueError('Resolved package lock missing')
        shutil.copy2(lock, output / 'packages-lock.json')
        evidence['resolved_packages'] = json.loads(lock.read_text(encoding='utf-8'))['dependencies']
        for package, requested in manifest['dependencies'].items():
            resolved = evidence['resolved_packages'].get(package, {}).get('version')
            if not resolved or (not requested.startswith('file:') and resolved != requested):
                raise ValueError('Resolved package lock does not match requested exact dependency: ' + package)
        for name in fixture.get('required_artifacts', []):
            artifact = output / name
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise ValueError('Required smoke artifact missing: ' + name)
        if fixture.get('requires_graphics'):
            graphics = json.loads((output / 'graphics-device.json').read_text(encoding='utf-8'))
            if graphics.get('deviceType') == 'Null':
                evidence['status'], evidence['observation'] = 'BLOCKED_NOT_RUN', 'not_observed'
                raise RuntimeError('Measured graphics device unavailable in readback metadata')
            if (graphics.get('editorVersion') != version or not graphics.get('deviceType')
                    or float(graphics.get('pixelVariation', 0)) <= 0.1):
                raise ValueError('Measured graphics/readback evidence does not satisfy render smoke')
            if not (output / 'pipeline-smoke.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Render smoke screenshot is not a PNG')
            evidence['graphics_observation'] = graphics
        evidence['status'], evidence['reason'], code = 'PASS', 'Nonempty EditMode tests passed', 0
    except (OSError, ValueError, RuntimeError, ET.ParseError, KeyError, TypeError, subprocess.SubprocessError) as error:
        evidence['reason'] = str(error)
        code = 2 if evidence['status'] == 'BLOCKED_NOT_RUN' else 1
    finally:
        try:
            final_inputs = input_hashes(ROOT, source, local_inputs, MATRIX)
            evidence['input_hashes_after'] = final_inputs
            evidence['source_changed_during_execution'] = final_inputs != initial_inputs
            if final_inputs != initial_inputs:
                evidence['status'], evidence['reason'], code = 'FAIL', 'Protected inputs changed during execution', 1
        except (OSError, ValueError) as error:
            evidence['status'], evidence['reason'], code = 'FAIL', 'Input rehash failed: ' + str(error), 1
        if project is not None and project.exists():
            try:
                for name in ('manifest.json', 'packages-lock.json'):
                    path = project / 'Packages' / name
                    if path.exists():
                        shutil.copy2(path, output / name)
            except OSError as error:
                evidence['pre_cleanup_outcome'] = dict(status=evidence['status'],
                    reason=evidence['reason'], exit_code=code)
                evidence['status'], evidence['reason'], code = (
                    'FAIL', 'Could not retain Unity package evidence: ' + str(error), 1)
        if workspace is not None:
            try:
                evidence['cleanup_retries'] = cleanup_workspace(workspace)
            except OSError as error:
                # Unity PackageCache may still be changing after Editor exits.
                # Never turn a real Editor failure into argparse "unsafe paths".
                # Keep the original outcome and write evidence even if cleanup fails.
                evidence['pre_cleanup_outcome'] = dict(status=evidence['status'],
                    reason=evidence['reason'], exit_code=code)
                evidence['workspace_cleanup_error'] = str(error)
                evidence['workspace_cleanup_path'] = workspace.name
                evidence['status'], evidence['reason'], code = (
                    'FAIL', 'Temporary Unity workspace cleanup failed: ' + str(error), 1)
        if not (output / 'editor.log').exists():
            (output / 'editor.log').write_text(evidence['status'] + ': ' + evidence['reason'] + '\n', encoding='utf-8')
        for name in ('editor.stdout.log', 'editor.stderr.log'):
            if not (output / name).exists():
                (output / name).write_text('BLOCKED_NOT_RUN: no Editor test process executed; ' + evidence['reason'] + '\n', encoding='utf-8')
        evidence['artifact_hashes'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in output.iterdir() if path.is_file()}
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        summary = os.getenv('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary, 'a', encoding='utf-8') as stream:
                stream.write(f"Unity {fixture['id']}: **{evidence['status']}** — {evidence['reason']}\n")
        print(f"{fixture['id']}: {evidence['status']} ({evidence['reason']})")
    return code

def main(argv=None):
    # Redirected Windows consoles may use a legacy code page. Diagnostics must
    # never change a FAIL exit into argparse's BLOCKED/invalid-input exit.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--canary', action='store_true')
    parser.add_argument('--editor', help='Direct Unity.exe (Windows) or Unity (Linux); overrides UNITY_EDITOR')
    parser.add_argument('--editor-root', help='Directory containing <exact-version>/Editor/Unity[.exe]')
    parser.add_argument('--timeout', type=int, default=3600, help='Editor test process timeout in seconds')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.fixture not in {row['id'] for row in json.loads(MATRIX.read_text(encoding='utf-8'))['fixtures']}:
        parser.error('Unknown fixture: ' + args.fixture)
    try:
        return run(args)
    except (OSError, ValueError) as error:
        parser.error('Unsafe or invalid input/output paths: ' + str(error))


if __name__ == '__main__':
    sys.exit(main())
