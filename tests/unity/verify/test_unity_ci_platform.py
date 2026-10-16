"""Host regressions only; synthetic executions never certify a Unity Editor."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import unity_ci as ci


class EditorDiscoveryTests(unittest.TestCase):
    def editor(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('host test placeholder', encoding='utf-8')
        path.chmod(0o755)
        return path.resolve()

    def test_exact_hub_layout_on_windows_and_linux(self):
        for system, name in [('Windows', 'Unity.exe'), ('Linux', 'Unity')]:
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'Unity Hub 日本語'
                expected = self.editor(root / '6000.6.0f1/Editor' / name)
                self.editor(root / '6000.3.12f1/Editor' / name)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(ci.find_editor('6000.6.0f1', editor_root=root, system=system), expected)

    def test_windows_default_program_files_hub(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.editor(root / 'Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe')
            with patch.dict(os.environ, {'ProgramFiles': str(root)}, clear=True):
                self.assertEqual(ci.find_editor('6000.6.0f1', system='Windows'), expected)

    def test_linux_default_user_hub(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.editor(root / 'Unity/Hub/Editor/6000.6.0f1/Editor/Unity')
            with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=root):
                self.assertEqual(ci.find_editor('6000.6.0f1', system='Linux'), expected)

    def test_direct_editor_overrides_root_and_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            direct = self.editor(root / 'Direct Editor 日本語/Unity.exe')
            other = self.editor(root / '6000.6.0f1/Editor/Unity.exe')
            with patch.dict(os.environ, {'UNITY_EDITOR': str(other)}, clear=True):
                self.assertEqual(ci.find_editor('6000.6.0f1', editor=direct, editor_root=root, system='Windows'), direct)

    def test_environment_editor_and_root_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.editor(root / '6000.6.0f1/Editor/Unity.exe')
            for env in [{'UNITY_EDITOR': str(expected)}, {'UNITY_EDITOR_ROOT': str(root)}]:
                with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                    self.assertEqual(ci.find_editor('6000.6.0f1', system='Windows'), expected)

    def test_missing_override_never_falls_back_to_another_editor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.editor(root / 'Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe')
            with patch.dict(os.environ, {'ProgramFiles': str(root)}, clear=True):
                for kwargs in [{'editor': root / 'missing.exe'}, {'editor_root': root / 'missing'}]:
                    with self.subTest(kwargs=kwargs), self.assertRaises(RuntimeError):
                        ci.find_editor('6000.6.0f1', system='Windows', **kwargs)

    @unittest.skipIf(os.name == 'nt', 'POSIX execute permission test')
    def test_nonexecutable_linux_editor_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            editor = self.editor(Path(temporary) / 'Unity')
            editor.chmod(0o644)
            with self.assertRaises(RuntimeError):
                ci.find_editor('6000.6.0f1', editor=editor, system='Linux')

    def test_unsupported_host_cannot_launch_or_download_linux_editor(self):
        with self.assertRaises(RuntimeError):
            ci.find_editor('6000.6.0f1', editor=sys.executable, system='Darwin')


class PlatformPreflightTests(unittest.TestCase):
    def test_canary_invalid_explicit_root_never_downloads_a_replacement(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                'UNITY_LICENSE_READY': 'true', 'UNITY_EDITOR': '', 'UNITY_EDITOR_ROOT': '',
                'UNITY_ALLOW_EDITOR_DOWNLOAD': 'true'}), patch.object(ci.platform, 'system', return_value='Linux'), \
                patch.object(ci, 'resolve_release', return_value={'version': '6000.7.0a1'}), \
                patch.object(ci, 'download_editor', side_effect=RuntimeError('unexpected download')) as download:
            args = argparse.Namespace(fixture='minimal-6000.6', output=temporary, canary=True,
                                      editor_root=str(Path(temporary) / 'missing root'))
            self.assertEqual(ci.run(args), 2)
            download.assert_not_called()

    def test_non_utf8_console_cannot_turn_timeout_failure_into_blocked(self):
        script = '''
import sys, subprocess
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import unity_ci as ci
def execute(command, **kwargs):
    if '-version' in command:
        return subprocess.CompletedProcess(command, 0, '6000.6.0f1', '')
    raise subprocess.TimeoutExpired(command, 1)
with patch.object(ci.subprocess, 'run', side_effect=execute):
    sys.exit(ci.main(['--fixture', 'minimal-6000.6', '--output', sys.argv[2], '--editor', sys.executable]))
'''
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / '\u6210\u679c\u7269 with spaces'
            result = subprocess.run([sys.executable, '-c', script, str(ci.ROOT / 'ci/verify'), str(output)],
                env=dict(os.environ, UNITY_LICENSE_READY='true', PYTHONIOENCODING='ascii', GITHUB_SHA='f'*40),
                capture_output=True, text=True, encoding='ascii', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / 'evidence.json').read_text(encoding='utf-8'))['status'], 'FAIL')

    def test_non_utf8_console_cannot_change_blocked_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'artifacts'
            missing = Path(temporary) / '\u6210\u679c\u7269/Unity.exe'
            result = subprocess.run([sys.executable, str(ci.ROOT / 'tests/unity/verify/unity_ci.py'),
                '--fixture', 'minimal-6000.6', '--output', str(output), '--editor', str(missing)],
                env=dict(os.environ, UNITY_LICENSE_READY='true', PYTHONIOENCODING='ascii'),
                capture_output=True, text=True, encoding='ascii', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / 'evidence.json').read_text(encoding='utf-8'))['status'], 'BLOCKED_NOT_RUN')

    def test_wrong_version_blocks_before_test_launch(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                'UNITY_LICENSE_READY': 'true', 'UNITY_EDITOR': sys.executable}), \
                patch.object(ci.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '6000.3.12f1', '')) as execute:
            self.assertEqual(ci.run(argparse.Namespace(fixture='minimal-6000.6', output=temporary, canary=False)), 2)
            evidence = json.loads((Path(temporary) / 'evidence.json').read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'], 'BLOCKED_NOT_RUN')
            self.assertNotIn('observed_editor', evidence)
            self.assertFalse(evidence['editor_test_process_started'])
            self.assertEqual(sum('-version' in call.args[0] for call in execute.call_args_list), 1)
            self.assertFalse(any('-runTests' in call.args[0] for call in execute.call_args_list))


@unittest.skipUnless(shutil.which('pwsh') or shutil.which('powershell'), 'PowerShell is unavailable on this host')
class PowerShellEntrypointTests(unittest.TestCase):
    def test_script_from_other_cwd_preserves_blocked_code_and_unicode_paths(self):
        shell = shutil.which('pwsh') or shutil.which('powershell')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / '成果物 with spaces'
            env = dict(os.environ, UNITY_LICENSE_READY='false')
            command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                       str(ci.ROOT / 'tests/unity/scripts/run-unity-tests.ps1'), '-Fixture', 'minimal-6000.6',
                       '-OutputDirectory', str(output), '-PythonCommand', sys.executable]
            result = subprocess.run(command, cwd=temporary, env=env, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            evidence = json.loads((output / 'evidence.json').read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'], 'BLOCKED_NOT_RUN')
            self.assertNotIn('tests_passed', evidence)

    def test_explicit_editor_path_with_spaces_reaches_runner(self):
        shell = shutil.which('pwsh') or shutil.which('powershell')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'artifacts'
            missing = Path(temporary) / 'Missing Unity Editor/Unity.exe'
            env = dict(os.environ, UNITY_LICENSE_READY='true', UNITY_EDITOR=sys.executable)
            result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ci.ROOT / 'tests/unity/scripts/run-unity-tests.ps1'), '-Fixture', 'minimal-6000.6',
                '-OutputDirectory', str(output), '-EditorPath', str(missing), '-PythonCommand', sys.executable],
                cwd=temporary, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            evidence = json.loads((output / 'evidence.json').read_text(encoding='utf-8'))
            self.assertIn(str(missing), evidence['reason'])
            self.assertEqual(evidence['status'], 'BLOCKED_NOT_RUN')


@unittest.skipIf(os.name == 'nt', 'Linux shell entrypoint test')
class ShellEntrypointTests(unittest.TestCase):
    def test_blocked_exit_from_another_cwd_with_unicode_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / '成果物 with spaces'
            result = subprocess.run(['bash', str(ci.ROOT / 'tests/unity/scripts/run-unity-tests.sh'),
                '--fixture', 'minimal-6000.6', '--output', str(output)], cwd=temporary,
                env=dict(os.environ, UNITY_CI_PYTHON=sys.executable, UNITY_LICENSE_READY='false'),
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(json.loads((output / 'evidence.json').read_text(encoding='utf-8'))['status'], 'BLOCKED_NOT_RUN')


if __name__ == '__main__':
    unittest.main()
