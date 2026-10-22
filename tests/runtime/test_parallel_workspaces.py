import os
from pathlib import Path
import tempfile
import unittest

from unityagent.runtime.tooling.environment.discovery import discover_environment


class ParallelWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = self.project('original')
        self.workers = []
        for name in ('left', 'right'):
            project = self.project(name)
            snapshot = discover_environment(str(project), editor_processes=[], editor_processes_observed=True).to_dict()
            self.workers.append({'task_id': name, 'workspace': str(project),
                'output_root': str(self.root / (name + '-output')), 'environment_snapshot': snapshot})

    def project(self, name):
        project = self.root / name
        for child in ('Assets', 'Packages', 'ProjectSettings'):
            (project / child).mkdir(parents=True)
        (project / 'Assets/C.cs').write_text('class C {}')
        (project / 'Packages/manifest.json').write_text('{"dependencies":{}}')
        (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.15f1\n')
        (project / '.git/objects').mkdir(parents=True)
        (project / '.git/HEAD').write_text('ref: refs/heads/fixture\n')
        return project

    def verify(self):
        from unityagent.runtime.sandbox.parallel_workspaces import verify_worker_workspaces
        return verify_worker_workspaces(self.original, self.workers)

    def test_distinct_physical_projects_and_outputs_are_verified(self):
        result = self.verify()
        self.assertEqual(result['status'], 'verified', result)
        self.assertEqual(set(result['workspaces']), {'left', 'right'})
        self.assertNotEqual(result['workspaces']['left']['physical_identity'],
                            result['workspaces']['right']['physical_identity'])

    def test_original_project_or_its_alias_is_never_a_worker(self):
        for alias in (False, True):
            target = self.original
            if alias:
                target = self.root / 'alias'
                target.symlink_to(self.original, target_is_directory=True)
            self.workers[0]['workspace'] = str(target)
            with self.assertRaises(ValueError):
                self.verify()

    def test_hardlinked_source_is_rejected_before_dispatch(self):
        source = Path(self.workers[0]['workspace']) / 'Assets/C.cs'
        source.unlink()
        os.link(self.original / 'Assets/C.cs', source)
        with self.assertRaises(ValueError):
            self.verify()

    def test_directory_symlink_inside_worker_is_rejected(self):
        assets = Path(self.workers[0]['workspace']) / 'Assets'
        (assets / 'external').symlink_to(self.original / 'Assets', target_is_directory=True)
        with self.assertRaises(ValueError):
            self.verify()

    def test_shared_output_and_output_inside_original_are_rejected(self):
        for output in (self.workers[0]['output_root'], str(self.original / 'output')):
            self.workers[1]['output_root'] = output
            with self.assertRaises(ValueError):
                self.verify()

    def test_uncreated_outputs_with_the_same_physical_ancestor_and_tail_are_rejected(self):
        from unittest.mock import patch
        from unityagent.runtime.sandbox import parallel_workspaces as workspaces
        first, second = self.root / 'external-first', self.root / 'external-second'
        first.mkdir()
        second.mkdir()
        identity = workspaces._identity
        for left, right in ((first / 'output', second / 'output'), (first, second / 'nested')):
            with self.subTest(left=left, right=right):
                self.workers[0]['output_root'], self.workers[1]['output_root'] = str(left), str(right)
                with patch.object(workspaces, '_identity', side_effect=lambda path: identity(first if path == second else path)):
                    with self.assertRaises(ValueError):
                        self.verify()

    def test_output_directory_replacement_changes_the_physical_binding(self):
        output = Path(self.workers[0]['output_root'])
        output.mkdir()
        before = self.verify()
        output.rename(self.root / 'old-output')
        output.mkdir()
        after = self.verify()
        self.assertNotEqual(before['workspaces']['left'], after['workspaces']['left'])

    def test_output_ancestor_aliasing_another_outputs_descendant_is_rejected(self):
        from unittest.mock import patch
        from unityagent.runtime.sandbox import parallel_workspaces as workspaces
        first, alias = self.root / 'external-first', self.root / 'external-alias'
        nested = first / 'nested'
        nested.mkdir(parents=True)
        alias.mkdir()
        identity = workspaces._identity
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                outputs = [str(first), str(alias / 'new')]
                if reverse:
                    outputs.reverse()
                for worker, output in zip(self.workers, outputs):
                    worker['output_root'] = output
                with patch.object(workspaces, '_identity', side_effect=lambda path: identity(nested if path == alias else path)):
                    with self.assertRaises(ValueError):
                        self.verify()

    def test_shared_git_common_directory_disables_parallel(self):
        common = self.root / 'shared-git'
        common.mkdir()
        (common / 'objects').mkdir()
        (common / 'HEAD').write_text('ref: refs/heads/fixture\n')
        for worker in self.workers:
            gitdir = self.root / (worker['task_id'] + '-git')
            gitdir.mkdir()
            (gitdir / 'commondir').write_text(str(common))
            import shutil
            marker = Path(worker['workspace']) / '.git'
            shutil.rmtree(marker)
            marker.write_text('gitdir: ' + str(gitdir))
        result = self.verify()
        self.assertEqual(result['status'], 'serial')
        self.assertIn('shared_git_directory', result['reasons'])

    def test_unknown_or_shared_editor_state_disables_parallel_without_faking_facts(self):
        for running in ('unknown', True):
            self.workers[0]['environment_snapshot']['unity_editor']['running'] = running
            result = self.verify()
            self.assertEqual(result['status'], 'serial')
            self.assertEqual(self.workers[0]['environment_snapshot']['unity_editor']['running'], running)

    def test_wrong_project_binding_is_rejected(self):
        self.workers[0]['environment_snapshot']['project']['root'] = str(self.original)
        with self.assertRaises(ValueError):
            self.verify()

    def test_git_pointer_and_common_directory_cannot_hide_symlink_aliases(self):
        import shutil
        for common in (False, True):
            with self.subTest(common=common):
                project = Path(self.workers[0]['workspace'])
                marker = project / '.git'
                if marker.is_dir():
                    shutil.rmtree(marker)
                elif marker.exists():
                    marker.unlink()
                real = self.root / ('real-git-' + str(common))
                (real / 'objects').mkdir(parents=True)
                (real / 'HEAD').write_text('ref: refs/heads/fixture\n')
                alias = self.root / ('git-alias-' + str(common))
                alias.symlink_to(real, target_is_directory=True)
                if common:
                    directory = self.root / 'worktree-git'
                    directory.mkdir()
                    (directory / 'commondir').write_text(str(alias))
                else:
                    directory = alias
                marker.write_text('gitdir: ' + str(directory))
                with self.assertRaises(ValueError):
                    self.verify()

    def test_shared_physical_asset_directory_is_rejected_even_without_a_symlink(self):
        from unittest.mock import patch
        from unityagent.runtime.sandbox import parallel_workspaces as workspaces
        identity = workspaces._identity
        original_assets = self.original / 'Assets'
        clone_assets = Path(self.workers[0]['workspace']) / 'Assets'
        def aliased(path):
            return identity(original_assets if path == clone_assets else path)
        with patch.object(workspaces, '_identity', side_effect=aliased):
            with self.assertRaises(ValueError):
                self.verify()
