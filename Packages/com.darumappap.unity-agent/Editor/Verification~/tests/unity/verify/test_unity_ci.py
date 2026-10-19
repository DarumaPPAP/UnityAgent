import json
import os
from pathlib import Path
import tempfile
import unittest
import argparse
import subprocess
import sys
from unittest.mock import patch, Mock
import unity_ci as ci

class ReleaseResolverTests(unittest.TestCase):
    def release(self, version='6000.7.0a9', url='https://download.unity3d.com/x/editor.tar.xz'):
        return dict(version=version, shortRevision='abc123', downloads=[dict(platform='LINUX',architecture='X86_64',type='TAR_XZ',url=url)])

    def test_latest_numeric_prerelease_next_stream(self):
        rows=[self.release('6000.7.0a9'), self.release('6000.7.0a10'),self.release('6000.6.0b99'),self.release('6000.8.0f1')]
        self.assertEqual(ci.select_release({'results':rows},'6000.6.0f1')['version'],'6000.7.0a10')

    def test_stable_wrong_stream_missing_archive_untrusted_url_rejected(self):
        for row in [self.release('6000.6.0b1'), self.release('6000.7.0f1'), self.release(url='https://evil.test/archive'), self.release(url='http://download.unity3d.com/editor')]:
            with self.subTest(row=row),self.assertRaises(ValueError):
                ci.select_release({'results':[row]},'6000.6.0f1')
        row=self.release();row['downloads'][0]['architecture']='ARM64'
        with self.assertRaises(ValueError):ci.select_release({'results':[row]},'6000.6.0f1')

    def test_pagination_not_first_row_assumption(self):
        pages=[{'results':[self.release('6000.7.0a9')],'total':2},{'results':[self.release('6000.7.0a10')],'total':2}]
        with patch.object(ci,'fetch',side_effect=pages) as fetch:
            self.assertEqual(ci.resolve_release('6000.6.0f1')['version'],'6000.7.0a10')
            self.assertIn('offset=1',fetch.call_args.args[0])

class RegistryTests(unittest.TestCase):
    def test_exact_stream_stable_minimum_patch(self):
        payload={'versions':{'17.6.1':{'unity':'6000.6','unityRelease':'0f1'},
            '17.6.2':{'unity':'6000.6','unityRelease':'1f1'},
            '17.6.3-pre.1':{'unity':'6000.6'},'17.7.0':{'unity':'6000.7'},
            '17.5.9':{'unity':'6000.5'}}}
        self.assertEqual(ci.package_version(payload,'6000.6.0f1'),'17.6.1')
    def test_no_exact_stream_rejected(self):
        with self.assertRaises(ValueError):
            ci.package_version({'versions':{'17.5.0':{'unity':'6000.5'}}},'6000.6.0f1')

class EvidenceTests(unittest.TestCase):
    def evaluate(self,xml):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'results.xml';path.write_text(xml)
            return ci.test_evidence(path)
    def test_nonempty_pass(self):
        self.assertEqual(self.evaluate('<test-run result="Passed" total="1" passed="1"><test-case result="Passed"/></test-run>'),1)
    def test_zero_skipped_failed_inconclusive_bad_totals_rejected(self):
        examples=['<test-run result="Passed" total="0" passed="0"/>',
          '<test-run result="Passed" total="1" passed="1"><test-case result="Skipped"/></test-run>',
          '<test-run result="Passed" total="1" passed="1"><test-case result="Inconclusive"/></test-run>',
          '<test-run result="Failed" total="1" passed="0"><test-case result="Failed"/></test-run>',
          '<test-run result="Passed" total="2" passed="2"><test-case result="Passed"/></test-run>',
          '<test-run result="Passed" total="1" passed="1" skipped="1"><test-case result="Passed"/></test-run>']
        for xml in examples:
            with self.subTest(xml=xml),self.assertRaises(ValueError):self.evaluate(xml)

    def test_missing_license_generates_blocked_artifacts_not_pass(self):
        import argparse
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,{'UNITY_LICENSE_READY':'false'}):
            args=argparse.Namespace(fixture='minimal-6000.6',output=temporary,canary=False)
            self.assertEqual(ci.run(args),2)
            evidence=json.loads((Path(temporary)/'evidence.json').read_text())
            self.assertEqual(evidence['status'],'BLOCKED_NOT_RUN')
            self.assertEqual(evidence['requested_editor'],'6000.6.0f1')
            self.assertIn('com.unity.pipeline',evidence['packages'])
            self.assertTrue((Path(temporary)/'editor.log').exists())
            self.assertNotIn('tests_passed',evidence)

class TestStagingTests(unittest.TestCase):
    def test_canonical_discovers_existing_unassembled_tests_in_disposable_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); package = root/'package'; project = root/'project'
            source = package/'Tests/Editor'; source.mkdir(parents=True)
            test = source/'ExistingTests.cs'; test.write_text('class ExistingTests {}')
            inventory = ci.stage_artist_tests(package, project)
            self.assertEqual(len(inventory),1)
            self.assertTrue((project/'Assets/CiArtistPackageTests/CiArtistPackageTests.asmdef').is_file())
            self.assertEqual(test.read_text(),'class ExistingTests {}')
            self.assertFalse((source/'CiArtistPackageTests.asmdef').exists())

class RunnerTests(unittest.TestCase):
    def run_fake(self, mode, cleanup_error=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / 'fixture'
            (project / 'Packages').mkdir(parents=True)
            (project / 'ProjectSettings').mkdir()
            (project / 'Packages/manifest.json').write_text('{"dependencies":{"com.unity.test-framework":"1.3.9"}}')
            (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.6.0f1')
            matrix = root / 'matrix.yaml'
            matrix.write_text(json.dumps({'canonical_editor':'6000.6.0f1','package_policy':'test',
                'fixtures':[dict(id='fake',project='fixture',pipeline='builtin',editor='6000.6.0f1',
                    requires_graphics=mode.startswith('render-'),
                    required_artifacts=['pipeline-smoke.png','graphics-device.json'] if mode.startswith('render-') else [])]}))
            output = root / 'artifacts'; output.mkdir()
            (output/'project').mkdir(); (output/'project/unowned.txt').write_text('preserve')
            # A prior successful result must never satisfy a new run.
            (output / 'results.xml').write_text('<test-run result="Passed" total="1" passed="1"><test-case result="Passed"/></test-run>')
            def execute(command, **kwargs):
                if '-version' in command:
                    return subprocess.CompletedProcess(command,0,'6000.6.0f1','')
                kwargs['stdout'].write('Editor stdout evidence\n'); kwargs['stdout'].flush()
                kwargs['stderr'].write('Editor stderr evidence\n'); kwargs['stderr'].flush()
                log = Path(command[command.index('-logFile')+1])
                if mode == 'launch-error':
                    raise OSError('Editor process could not start')
                if mode == 'timeout':
                    log.write_text('Editor started but timed out')
                    raise subprocess.TimeoutExpired(command, 3600)
                if mode == 'malformed-results':
                    log.write_text('Editor ran with invalid NUnit')
                    Path(command[command.index('-testResults')+1]).write_text('<test-run')
                    return subprocess.CompletedProcess(command, 0)
                if mode == 'license':
                    log.write_text('No valid license found')
                    return subprocess.CompletedProcess(command,1)
                if mode == 'graphics':
                    log.write_text('UNITY_CI_GRAPHICS_UNAVAILABLE: graphicsDeviceType=Null')
                    return subprocess.CompletedProcess(command, 0)
                log.write_text('Editor test execution')
                if mode.startswith('render-'):
                    self.assertNotIn('-nographics',command)
                else:
                    self.assertIn('-nographics',command)
                if mode in {'pass','source-mutation','assertion-fail'} or mode.startswith('render-'):
                    Path(command[command.index('-testResults')+1]).write_text('<test-run result="Passed" total="1" passed="1"><test-case result="Passed"/></test-run>')
                    copied = Path(command[command.index('-projectPath')+1])
                    (copied / 'Packages/packages-lock.json').write_text('{"dependencies":{"com.unity.test-framework":{"version":"1.3.9"}}}')
                if mode == 'assertion-fail':
                    Path(command[command.index('-testResults')+1]).write_text('<test-run result="Failed" total="1" passed="0"><test-case result="Failed"/></test-run>')
                    return subprocess.CompletedProcess(command, 1)
                if mode == 'source-mutation':
                    (project/'ProjectSettings/ProjectVersion.txt').write_text('mutated during execution')
                if mode in {'render-valid','render-null'}:
                    (output/'pipeline-smoke.png').write_bytes(b'\x89PNG\r\n\x1a\nHOST_TEST_ONLY')
                    (output/'graphics-device.json').write_text(json.dumps({'editorVersion':'6000.6.0f1','deviceType':'Null' if mode=='render-null' else 'Vulkan','pixelVariation':0.7}))
                return subprocess.CompletedProcess(command,0)
            with patch.object(ci,'ROOT',root), patch.object(ci,'MATRIX',matrix), patch.object(ci.subprocess,'run',side_effect=execute), patch.dict(os.environ,{'UNITY_EDITOR':sys.executable,'UNITY_LICENSE_READY':'true','UNITY_GRAPHICS_READY':'true','GITHUB_SHA':'f'*40}):
                if cleanup_error is None:
                    code = ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False))
                else:
                    with patch.object(ci, 'cleanup_workspace', side_effect=cleanup_error):
                        code = ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False))
            self.assertEqual((output/'project/unowned.txt').read_text(),'preserve')
            if cleanup_error is None:
                self.assertEqual(list(output.glob('unity-ci-owned-*')),[])
            evidence = json.loads((output / 'evidence.json').read_text())
            evidence['_stdout'] = (output / 'editor.stdout.log').read_text()
            evidence['_stderr'] = (output / 'editor.stderr.log').read_text()
            return code, evidence
    def test_persistent_winerror_145_remains_failure_after_bounded_retries(self):
        retryable = OSError(145, 'directory not empty')
        retryable.winerror = 145
        temporary = Mock()
        temporary.cleanup.side_effect = retryable
        with patch.object(ci.time, 'sleep') as sleep, self.assertRaises(OSError):
            ci.cleanup_workspace(temporary)
        self.assertEqual(temporary.cleanup.call_count, 7)
        self.assertEqual(sleep.call_count, 6)

    def test_cleanup_winerror_145_is_retried_but_other_errors_fail_immediately(self):
        retryable = OSError(145, 'directory not empty')
        retryable.winerror = 145
        temporary = Mock()
        temporary.cleanup.side_effect = [retryable, retryable, None]
        with patch.object(ci.time, 'sleep') as sleep:
            self.assertEqual(ci.cleanup_workspace(temporary), 2)
        self.assertEqual(temporary.cleanup.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

        denied = OSError(13, 'permission denied')
        denied.winerror = 5
        temporary.cleanup.side_effect = denied
        temporary.cleanup.reset_mock()
        with patch.object(ci.time, 'sleep') as sleep, self.assertRaises(OSError):
            ci.cleanup_workspace(temporary)
        self.assertEqual(temporary.cleanup.call_count, 1)
        sleep.assert_not_called()

    def test_cleanup_failure_preserves_original_editor_failure_in_evidence(self):
        blocked = OSError(145, 'directory not empty')
        blocked.winerror = 145
        code, evidence = self.run_fake('assertion-fail', cleanup_error=blocked)
        self.assertEqual(code, 1)
        self.assertEqual(evidence['status'], 'FAIL')
        self.assertEqual(evidence['pre_cleanup_outcome']['status'], 'FAIL')
        self.assertIn('Editor returned exit code 1', evidence['pre_cleanup_outcome']['reason'])
        self.assertIn('directory not empty', evidence['workspace_cleanup_error'])
        self.assertIn('editor.log', evidence['artifact_hashes'])
        self.assertIn('results.xml', evidence['artifact_hashes'])

    def test_cleanup_failure_revokes_otherwise_passing_run(self):
        blocked = OSError(145, 'directory not empty')
        blocked.winerror = 145
        code, evidence = self.run_fake('pass', cleanup_error=blocked)
        self.assertEqual(code, 1)
        self.assertEqual(evidence['status'], 'FAIL')
        self.assertEqual(evidence['pre_cleanup_outcome']['status'], 'PASS')
        self.assertEqual(evidence['pre_cleanup_outcome']['exit_code'], 0)
        self.assertIn('Temporary Unity workspace cleanup failed', evidence['reason'])

    def test_launch_error_is_not_an_observed_test_failure(self):
        code, evidence = self.run_fake('launch-error')
        self.assertEqual(code, 2)
        self.assertEqual(evidence['status'], 'BLOCKED_NOT_RUN')
        self.assertEqual(evidence['observation'], 'not_observed')
        self.assertFalse(evidence['editor_test_process_started'])

    def test_timeout_after_launch_is_failure_with_logs(self):
        code, evidence = self.run_fake('timeout')
        self.assertEqual(code, 1)
        self.assertEqual(evidence['status'], 'FAIL')
        self.assertTrue(evidence['editor_test_process_started'])
        self.assertIn('editor.log', evidence['artifact_hashes'])

    def test_malformed_nunit_is_failure_with_evidence(self):
        code, evidence = self.run_fake('malformed-results')
        self.assertEqual(code, 1)
        self.assertEqual(evidence['status'], 'FAIL')
        self.assertIn('results.xml', evidence['artifact_hashes'])
    def test_assertion_failure_retains_nunit_and_package_lock(self):
        code, evidence = self.run_fake('assertion-fail')
        self.assertEqual(code, 1)
        self.assertEqual(evidence['status'], 'FAIL')
        self.assertEqual(evidence['observation'], 'observed')
        self.assertIn('results.xml', evidence['artifact_hashes'])
        self.assertIn('packages-lock.json', evidence['artifact_hashes'])
    def test_source_mutation_revokes_otherwise_passing_execution(self):
        code,evidence=self.run_fake('source-mutation')
        self.assertEqual(code,1);self.assertEqual(evidence['status'],'FAIL')
        self.assertTrue(evidence['source_changed_during_execution'])
        self.assertEqual(evidence['reason'],'Protected inputs changed during execution')
        self.assertEqual(evidence['tests_passed'],1)
    def test_render_requires_readback_artifacts(self):
        code,evidence=self.run_fake('render-missing')
        self.assertEqual(code,1);self.assertEqual(evidence['status'],'FAIL')
    def test_render_null_device_metadata_blocks_without_log_marker(self):
        code,evidence=self.run_fake('render-null')
        self.assertEqual(code,2);self.assertEqual(evidence['status'],'BLOCKED_NOT_RUN')
    def test_graphics_host_state_machine_checks_metadata_and_png(self):
        code,evidence=self.run_fake('render-valid')
        self.assertEqual(code,0);self.assertIn('graphics_observation',evidence)
    def test_stale_result_is_removed(self):
        code,evidence=self.run_fake('missing-results')
        self.assertEqual(code,1);self.assertEqual(evidence['status'],'FAIL')
    def test_license_fault_is_blocked(self):
        code,evidence=self.run_fake('license')
        self.assertEqual(code,2);self.assertEqual(evidence['status'],'BLOCKED_NOT_RUN')
    def test_observed_pass_requires_results_log_lock_and_exact_editor(self):
        code,evidence=self.run_fake('pass')
        self.assertEqual(code,0);self.assertEqual(evidence['tests_passed'],1)
        self.assertEqual(evidence['observed_editor'],'6000.6.0f1')
        self.assertIn('packages-lock.json',evidence['artifact_hashes'])
        self.assertEqual(evidence['source_identity']['commit'],'f'*40)
        self.assertFalse(evidence['source_changed_during_execution'])
        self.assertEqual(evidence['input_hashes'],evidence['input_hashes_after'])
        self.assertIn('editor.stdout.log',evidence['artifact_hashes'])
        self.assertIn('editor.stderr.log',evidence['artifact_hashes'])
        self.assertIn('Editor stdout evidence',evidence['_stdout'])
        self.assertIn('Editor stderr evidence',evidence['_stderr'])
    def test_stdout_and_stderr_survive_editor_failure(self):
        code,evidence=self.run_fake('license')
        self.assertEqual(code,2)
        self.assertIn('Editor stdout evidence',evidence['_stdout'])
        self.assertIn('Editor stderr evidence',evidence['_stderr'])
    def test_measured_null_graphics_blocks_even_zero_exit(self):
        code,evidence=self.run_fake('graphics')
        self.assertEqual(code,2);self.assertEqual(evidence['status'],'BLOCKED_NOT_RUN')

class PackageResolutionTests(unittest.TestCase):
    def test_p9_builtin_test_framework_160_matches_editor(self):
        requested = {'com.unity.render-pipelines.universal': '17.3.0',
                     'com.unity.test-framework': '1.6.0'}
        resolved = {'com.unity.render-pipelines.universal': {'version': '17.3.0', 'source': 'registry'},
                    'com.unity.test-framework': {'version': '1.6.0', 'source': 'builtin'}}
        ci.validate_resolved_dependencies(requested, resolved, 'p9-lts-urp')

    def test_p9_rejects_version_drift_and_nonbuiltin_framework(self):
        requested = {'com.unity.render-pipelines.universal': '17.3.0',
                     'com.unity.test-framework': '1.6.0'}
        for changed in ('version', 'source', 'urp'):
            with self.subTest(changed=changed):
                resolved = {'com.unity.render-pipelines.universal': {'version': '17.3.0', 'source': 'registry'},
                            'com.unity.test-framework': {'version': '1.6.0', 'source': 'builtin'}}
                if changed == 'version':
                    resolved['com.unity.test-framework']['version'] = '1.3.9'
                elif changed == 'source':
                    resolved['com.unity.test-framework']['source'] = 'registry'
                else:
                    resolved['com.unity.render-pipelines.universal']['version'] = '17.4.0'
                with self.assertRaises(ValueError):
                    ci.validate_resolved_dependencies(requested, resolved, 'p9-lts-urp')


class FixtureTests(unittest.TestCase):
    def test_p9_lts_is_canonical_and_does_not_run_g1_rock_workflow(self):
        config = json.loads(ci.MATRIX.read_text())
        self.assertEqual(config['canonical_editor'], '6000.3.12f1')
        fixture = next(f for f in config['fixtures'] if f['id'] == 'p9-lts-urp')
        self.assertEqual(fixture['editor'], '6000.3.12f1')
        self.assertEqual(fixture['test_filter'], 'UnityAgent.Production.LtsPreflightTests.UrpRenderGraphCapture')
        self.assertTrue(fixture['requires_graphics'])
        self.assertNotIn('RockProductionTests', fixture['test_filter'])
        self.assertNotIn('srp_package', fixture)
        dependencies = json.loads(
            (ci.ROOT / fixture['project'] / 'Packages/manifest.json').read_text())['dependencies']
        self.assertEqual(dependencies['com.unity.test-framework'], '1.6.0')
        self.assertEqual(dependencies['com.unity.render-pipelines.universal'], '17.3.0')
        preflight = (ci.ROOT / fixture['project'] / 'Assets/Editor/LtsPreflightTests.cs').read_text()
        # Host static contract only; real no-scene batch-mode behavior requires Editor E2E.
        self.assertIn('scene.isLoaded && scene.isActive', preflight)
        self.assertIn('if (hasRestorableSceneSetup)', preflight)
        self.assertIn('EditorSceneManager.RestoreSceneManagerSetup(previousScenes);', preflight)
        self.assertIn('if (ownsAssets)', preflight)
        self.assertIn('AssetDatabase.DeleteAsset(TemporaryRoot);', preflight)


    def test_63_fixture_exact_official_provenance_and_narrow_compile_scope(self):
        config=json.loads(ci.MATRIX.read_text())
        row=next(row for row in config['fixtures'] if row['id']=='minimal-6000.3')
        self.assertEqual(row['editor'],'6000.3.12f1')
        self.assertEqual(row['version_provenance']['commit'],'2d2e78cc9d6254bc6e7c9c5552cea053508e86cb')
        manifest=json.loads((ci.ROOT/row['project']/'Packages/manifest.json').read_text())
        self.assertNotIn('com.unity.pipeline',manifest['dependencies'])
        self.assertEqual(row['scope'],'compile-import')

    def test_fixtures_have_tests_scene_metadata_and_correct_local_package_path(self):
        config=json.loads(ci.MATRIX.read_text())
        for row in config['fixtures'][1:]:
            project=ci.ROOT/row['project']
            manifest=json.loads((project/'Packages/manifest.json').read_text())
            if row['id']=='p9-lts-urp':
                location=manifest['dependencies']['com.darumappap.unity-agent'][5:]
                self.assertEqual((project/'Packages'/location).resolve(),
                                 ci.ROOT/'Packages/com.darumappap.unity-agent')
                preflight=(project/'Assets/Editor/LtsPreflightTests.cs').read_text()
                self.assertIn('pixelVariation = variation',preflight)
                self.assertIn('RenderPipeline.SubmitRenderRequest',preflight)
                self.assertTrue((project/'Assets/Editor/LtsPreflightTests.cs.meta').is_file())
                continue
            location=manifest['dependencies']['com.darumappap.artist-subagent'][5:]
            self.assertEqual((project/'Packages'/location).resolve(),ci.ROOT/'subagent/artist_subagent/tools/editor')
            self.assertIn('[Test]',(project/'Assets/Editor/SmokeTests.cs').read_text())
            for asset in (project/'Assets').rglob('*'):
                if asset.suffix!='.meta':self.assertTrue(Path(str(asset)+'.meta').is_file(),asset)
            if row['scope']=='scene-native-api-smoke':
                scene=(project/'Assets/Scenes/PipelineSmoke.unity').read_text()
                self.assertIn('m_Name: Main Camera',scene)
                self.assertIn('m_Name: FovSubject',scene)
                self.assertIn('m_Name: Key Light',scene)
                script=(project/'Assets/Editor/SmokeTests.cs').read_text()
                self.assertIn('ReadPixels',script)
                self.assertIn('graphicsDeviceType == GraphicsDeviceType.Null',script)
                self.assertIn('Assert.Greater(maximum - minimum',script)
                self.assertTrue(row['requires_graphics'])
                self.assertIn('pipeline-smoke.png',row['required_artifacts'])
                if row['pipeline']!='builtin':self.assertIn('RenderPipeline.SubmitRenderRequest',script)


class ReplaySafetyTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'fixture'; package = root / 'package'
        (source / 'Packages').mkdir(parents=True); (source / 'Assets').mkdir(); (source / 'ProjectSettings').mkdir()
        (source / 'Assets/Subject.unity').write_text('scene source')
        (source / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.6.0f1')
        (source / 'Packages/manifest.json').write_text('{"dependencies":{"artist":"file:../../package"}}')
        package.mkdir(); (package / 'package.json').write_text('{"name":"artist","version":"1.0.0"}')
        (package / 'Code.cs').write_text('class Original {}'); (package / 'Code.cs.meta').write_text('guid: source')
        matrix=root/'matrix.yaml';matrix.write_text(json.dumps({'package_policy':'test','canonical_editor':'6000.6.0f1',
            'fixtures':[{'id':'fake','project':'fixture','editor':'6000.6.0f1','pipeline':'builtin'}]}))
        return source,package,matrix

    def test_blocked_replay_preserves_unowned_output_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            output=root/'artifacts';(output/'project').mkdir(parents=True)
            sentinel=output/'project/user-owned.txt';sentinel.write_text('preserve')
            with patch.object(ci,'ROOT',root),patch.object(ci,'MATRIX',matrix),patch.dict(os.environ,{'UNITY_LICENSE_READY':'false'}):
                self.assertEqual(ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False)),2)
            self.assertEqual(sentinel.read_text(),'preserve')

    def test_output_overlap_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            for output in [source,source/'new-output',package,package/'new-output',root]:
                with self.subTest(output=output),patch.object(ci,'ROOT',root),patch.object(ci,'MATRIX',matrix),patch.dict(os.environ,{'UNITY_LICENSE_READY':'false'}):
                    with self.assertRaises(ValueError):ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False))
                    self.assertEqual((package/'Code.cs').read_text(),'class Original {}')
                    self.assertEqual((source/'Assets/Subject.unity').read_text(),'scene source')
                    self.assertFalse((source/'evidence.json').exists())
                    self.assertFalse((package/'evidence.json').exists())

    def test_fixture_root_symlink_rejected_before_output_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            source.rename(root/'real-fixture');source.symlink_to(root/'real-fixture',target_is_directory=True)
            output=root/'new-artifacts'
            with patch.object(ci,'ROOT',root),patch.object(ci,'MATRIX',matrix),self.assertRaises(ValueError):
                ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False))
            self.assertFalse(output.exists())

    def test_input_hashes_change_for_scene_and_package_source_ignore_caches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            first=ci.input_hashes(root,source,{'artist':package},matrix)
            (package/'Library').mkdir();(package/'Library/cache.cs').write_text('generated')
            self.assertEqual(first,ci.input_hashes(root,source,{'artist':package},matrix))
            (package/'Code.cs').write_text('class Changed {}')
            second=ci.input_hashes(root,source,{'artist':package},matrix)
            self.assertNotEqual(first['digest'],second['digest'])
            (source/'Assets/Subject.unity').write_text('changed scene')
            self.assertNotEqual(second['digest'],ci.input_hashes(root,source,{'artist':package},matrix)['digest'])

    def test_output_root_symlink_rejected_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            (root/'real-output').mkdir();output=root/'output-link';output.symlink_to(root/'real-output',target_is_directory=True)
            with patch.object(ci,'ROOT',root),patch.object(ci,'MATRIX',matrix),self.assertRaises(ValueError):
                ci.run(argparse.Namespace(fixture='fake',output=str(output),canary=False))
            self.assertEqual(list((root/'real-output').iterdir()),[])

    def test_local_package_root_and_file_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            package.rename(root/'real-package');package.symlink_to(root/'real-package',target_is_directory=True)
            with patch.object(ci,'ROOT',root),patch.object(ci,'MATRIX',matrix),self.assertRaises(ValueError):
                ci.run(argparse.Namespace(fixture='fake',output=str(root/'output'),canary=False))
            package.unlink();(root/'real-package').rename(package)
            (package/'Code.cs').unlink();(package/'Code.cs').symlink_to(source/'Assets/Subject.unity')
            with self.assertRaises(ValueError):ci.input_hashes(root,source,{'artist':package},matrix)
            self.assertFalse((root/'output').exists())

    def test_input_hashes_include_meta_and_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source,package,matrix=self.fixture(root)
            first=ci.input_hashes(root,source,{'artist':package},matrix)
            self.assertIn('package/Code.cs.meta',first['files'])
            self.assertIn('package/package.json',first['files'])
            (package/'Code.cs.meta').write_text('changed meta')
            second=ci.input_hashes(root,source,{'artist':package},matrix)
            self.assertNotEqual(first['digest'],second['digest'])
            (package/'package.json').write_text('{"name":"artist","version":"2.0.0"}')
            self.assertNotEqual(second['digest'],ci.input_hashes(root,source,{'artist':package},matrix)['digest'])

if __name__ == '__main__': unittest.main()
