import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class ParallelCSharpE2ETests(unittest.TestCase):
    def tool(self):
        spec = importlib.util.spec_from_file_location('parallel_e2e', ROOT / 'tools/parallel_csharp_e2e.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def config(self, workspace, phase='prepare', **extra):
        return {'schema_version': '1.0', 'workspace_root': str(workspace), 'phase': phase,
                'model': 'explicit-model', 'timeout_seconds': 120, 'parallel_enabled': True, **extra}

    def test_prepare_never_overwrites_an_existing_workspace(self):
        tool = self.tool()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            user = workspace / 'user.txt'
            user.write_text('retain')
            with self.assertRaises(FileExistsError):
                tool.run(self.config(workspace))
            self.assertEqual(user.read_text(), 'retain')

    def test_missing_real_baseline_cannot_launch_workers_or_approve_any_patch(self):
        tool = self.tool()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'owned'
            with patch.object(tool, '_baseline', return_value={'status': 'unavailable'}):
                report = tool.run(self.config(workspace))
            self.assertEqual(report['status'], 'unavailable')
            self.assertFalse((workspace / 'left').exists())
            with self.assertRaises(ValueError):
                tool.run(self.config(workspace, phase='propose'))

    def test_owned_project_replacement_is_rejected_before_any_execution(self):
        import shutil
        tool = self.tool()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'owned'
            with patch.object(tool, '_baseline', return_value={'status': 'unavailable'}):
                tool.run(self.config(workspace))
            original = workspace / 'original'
            original.rename(workspace / 'old')
            shutil.copytree(workspace / 'old', original)
            with self.assertRaises(ValueError):
                tool.run(self.config(workspace, phase='propose'))
