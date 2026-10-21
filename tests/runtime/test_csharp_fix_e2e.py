import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import csharp_fix_e2e as e2e


class OwnedFixtureE2ETests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / 'new-owned-fixture'
        self.config = {'schema_version': '1.0', 'phase': 'prepare', 'workspace_root': str(self.workspace),
                       'model': 'gpt-fixture', 'timeout_seconds': 10}

    def unavailable(self, plane, project, config, entry, workspace):
        return {'status': 'blocked', 'results': [], 'evidence_refs': [],
                'result_revision': e2e.project_revision(project)}

    def test_unavailable_editor_is_saved_without_duplicate_launch_or_false_success(self):
        with patch.object(e2e, '_run', side_effect=self.unavailable) as runner:
            report = e2e.run(self.config)
        self.assertEqual(report['status'], 'unavailable')
        self.assertEqual(runner.call_count, 1)
        self.assertTrue((self.workspace / 'prepare-report.json').is_file())

    def test_prepare_never_overwrites_existing_directory(self):
        self.workspace.mkdir()
        marker = self.workspace / 'user.txt'
        marker.write_text('keep')
        with self.assertRaises(FileExistsError):
            e2e.run(self.config)
        self.assertEqual(marker.read_text(), 'keep')

    def test_no_apply_without_real_independent_test_failure(self):
        with patch.object(e2e, '_run', side_effect=self.unavailable):
            e2e.run(self.config)
        with patch.object(e2e, 'approve_csharp_fix') as approve:
            with self.assertRaisesRegex(ValueError, 'independent'):
                e2e.run({**self.config, 'phase': 'apply', 'approved_plan_id': '0' * 64})
        approve.assert_not_called()

    def test_project_directory_alias_or_replacement_is_not_an_owned_fixture(self):
        import shutil
        with patch.object(e2e, '_run', side_effect=self.unavailable):
            e2e.run(self.config)
        project = self.workspace / 'project'
        outside = self.workspace.parent / 'external-project'
        project.rename(outside)
        for alias in (True, False):
            if alias:
                project.symlink_to(outside, target_is_directory=True)
            else:
                shutil.copytree(outside, project)
            with patch.object(e2e, '_run') as runner:
                with self.assertRaisesRegex(ValueError, 'ownership|alias'):
                    e2e.run({**self.config, 'phase': 'propose'})
                runner.assert_not_called()
            if alias:
                project.unlink()
