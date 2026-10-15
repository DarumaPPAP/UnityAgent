import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unityagent.runtime.tooling.providers.unity_cli_loop.hot_reload_provider import HotReloadProvider, validate_hot_reload_result


class HotReloadTests(unittest.TestCase):
    def result(self):
        return {'Success':True, 'Outcome':'Applied', 'PatchedTotal':1, 'SkippedTotal':0,
                'FailedTotal':0, 'Methods':[{'Kind':'Patched','FilePath':'Assets/A.cs'}], 'IntroducedTypes':[]}

    def test_partial_skipped_failed_and_compile_fallback_are_not_hot_reload_success(self):
        validate_hot_reload_result(self.result())
        for change in ({'Outcome':'PartiallyApplied'}, {'Outcome':'ReplacedByCompile'},
                       {'SkippedTotal':1}, {'FailedTotal':1}, {'PatchedTotal':0},
                       {'Methods':[{'Kind':'Skipped'}]}, {'Success':False}):
            with self.assertRaises(ValueError): validate_hot_reload_result({**self.result(), **change})

    def test_binding_revision_approval_and_explicit_files_are_enforced(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)/'project'
            (project/'Assets').mkdir(parents=True)
            source = project/'Assets/A.cs'
            source.write_text('class A {}')
            binary = Path(root)/'uloop-project-runner'
            binary.write_bytes(b'pinned fixture binary')
            calls = []
            def runner(command, **kwargs):
                calls.append(command)
                output = {'Ready':True,'State':'Ready','IsPlaying':True} if 'status' in command else self.result()
                return SimpleNamespace(returncode=0,stdout=json.dumps(output),stderr='')
            provider = HotReloadProvider(project, binary,
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                check_approval=lambda _: None, command_runner=runner)
            request = {'schema_version':'1.0','capability':'editor.hot_reload','operation_kind':'editor_mutation',
                'project_root':str(project),'required_evidence':['editor_observation','mutation_evidence'],
                'mutation_scope':{'allowed_paths':['Assets/A.cs'],'prohibited_paths':['ProjectSettings']},
                'approval_ref':'approval','preferred_surface':'live_editor'}
            context = SimpleNamespace(policy_allowed=True,approval_complete=True)
            hashes = {'Assets/A.cs': hashlib.sha256(source.read_bytes()).hexdigest()}
            result = provider.execute(request, context, {'source_hashes':hashes})
            self.assertEqual(result['status'],'passed',result)
            self.assertEqual(result['normal_compile'],'not_observed')
            self.assertIn('--compile-on-skip',calls[-1])
            self.assertIn('off',calls[-1])
            self.assertIn('--project-path',calls[-1])
            source.write_text('changed')
            self.assertEqual(provider.execute(request,context,{'source_hashes':hashes})['status'],'failed')
            self.assertEqual(len(calls),2)

    def test_control_plane_keeps_compile_and_qa_unverified_after_successful_patch(self):
        from unittest.mock import patch
        from unityagent.cli import _fingerprint
        from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
        from unityagent.control_plane.hot_reload import plan_hot_reload, approve_hot_reload, apply_hot_reload
        from unityagent.runtime.tooling.environment.discovery import discover_environment
        from unityagent.runtime.execution_control.resource_lease import _lease_directory
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'project'
            for name in ('Assets','Packages','ProjectSettings'): (project/name).mkdir(parents=True)
            (project/'Assets/A.cs').write_text('class A {}')
            (project/'Packages/manifest.json').write_text('{"dependencies":{}}')
            (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.12f1\n')
            binary=root/'uloop-project-runner';binary.write_bytes(b'fixture')
            definition=_fingerprint()
            plan=plan_hot_reload(project,root/'state',['Assets/A.cs'],binary,
                hashlib.sha256(binary.read_bytes()).hexdigest(),definition)
            approval=approve_hot_reload(root/'state',plan['plan_id'])
            snapshot=discover_environment(project).to_dict()
            snapshot['unity_editor'].update(installed=True,running=True,project_bound=True,
                binding_status='bound',bound_instance_id='fixture-editor',safe_mode=False,project_version_match=True)
            snapshot['pipeline'].update(installed=True,reachable=True)
            calls=[]
            def command(_self,*args):
                calls.append(args)
                return {'State':'Ready','Ready':True,'IsPlaying':True} if args[0]=='status' else self.result()
            with patch('unityagent.control_plane.hot_reload.discover_environment',return_value=SimpleNamespace(to_dict=lambda:snapshot)), \
                 patch.object(HotReloadProvider,'_command',command), \
                 patch('unityagent.runtime.execution_control.resource_lease._lease_directory',
                       side_effect=lambda p,lease_root=None:_lease_directory(p,root/'leases')):
                result=apply_hot_reload(UnityAgentControlPlane(root/'state'),plan['plan_id'],
                    approval['approval_decision_id'],definition_fingerprint=definition)
            self.assertEqual(result['status'],'completed',result)
            self.assertEqual(result['acceptance'],'blocked')
            self.assertEqual(result['required_gates']['normal_compile'],'not_observed')
            self.assertTrue(result['evidence_refs'])
