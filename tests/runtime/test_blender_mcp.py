import tempfile
import unittest
from pathlib import Path
from unityagent.runtime.tooling.providers.blender_mcp.rock_job import RockJob


class Client:
    session_id = 'session-1'
    def __init__(self):
        self.calls = []
        self.timeout = False
    def tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.timeout: raise TimeoutError('uncertain')
        return {'content': [{'type': 'text', 'text': 'ok'}]}


class BlenderJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = Client()
        self.job = RockJob(self.root, self.client, check_approval=lambda digest: None)

    def test_timeout_is_durable_and_does_not_resubmit(self):
        self.client.timeout = True
        result = self.job.run('job-1', approval_ref='a')
        self.assertEqual(result['status'], 'uncertain')
        self.client.timeout = False
        result = self.job.run('job-1', approval_ref='a')
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(len(self.client.calls), 1)

    def test_only_reviewed_rock_template_is_sent_and_missing_artifact_is_not_passed(self):
        result = self.job.run('job-1', approval_ref='a')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.client.calls[0][0], 'execute_blender_code')
        code = self.client.calls[0][1]['code']
        self.assertIn('export_scene.fbx', code)
        self.assertNotIn('requests', code)
        with self.assertRaises(TypeError):
            self.job.run('job-2', approval_ref='a', code='arbitrary')

    def test_approval_is_required_and_rechecked(self):
        with self.assertRaises(ValueError): self.job.run('job', approval_ref='')
        self.job.check_approval = lambda _: (_ for _ in ()).throw(ValueError('revoked'))
        with self.assertRaisesRegex(ValueError, 'revoked'): self.job.run('job', approval_ref='a')
        self.assertEqual(self.client.calls, [])


class RockControlPlaneTests(unittest.TestCase):
    def test_approved_job_uses_broker_and_persists_evidence_without_unity_lease(self):
        import json, hashlib
        from unittest.mock import patch
        from unityagent.cli import _fingerprint
        from unityagent.control_plane.unity_agent_control_plane import UnityAgentControlPlane
        from unityagent.control_plane.rock_artifact import plan_rock, approve_rock, apply_rock
        from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'Project'
            for name in ('Assets', 'Packages', 'ProjectSettings'):
                (project/name).mkdir(parents=True)
            (project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.15f1\n')
            (project/'Packages/manifest.json').write_text('{"dependencies":{}}')
            state = root/'state'
            definition = _fingerprint()
            plan = plan_rock(project, state, 'fixture-rock', definition)
            approval = approve_rock(state, plan['plan_id'])
            client = Client()
            client.identity = {'protocolVersion':'2024-11-05', 'serverInfo': {'name':'fixture','version':'1'}}
            client.tools = {'execute_blender_code'}
            def create_fixture(name, arguments):
                folder = state/'blender-jobs/fixture-rock'
                (folder/'Rock.fbx').write_bytes(b'fixture FBX; not production evidence')
                (folder/'artifact.json').write_text(json.dumps({'sha256':hashlib.sha256((folder/'Rock.fbx').read_bytes()).hexdigest(),
                    'vertices':42,'triangles':80,'scale':[1,1,1],'uv_layers':1,'texture_dependencies':[]}))
                return {'content':[{'type':'text','text':'fixture'}]}
            client.tool = create_fixture
            plane = UnityAgentControlPlane(state)
            with patch('unityagent.runtime.dispatcher.tool_runtime_dispatcher.RuntimeProjectLease', side_effect=AssertionError('Unity Lease held during Blender')):
                result = apply_rock(plane, plan['plan_id'], approval['approval_decision_id'], client, definition_fingerprint=definition)
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(len(result['evidence_refs']), 1)
            self.assertFalse(result['verified'])
            self.assertEqual(result['unity_import'], 'BLOCKED_NOT_RUN')
            ApprovalDecisionStore(state).revoke(approval['approval_decision_id'])
            with self.assertRaisesRegex(ValueError, 'revoked'):
                apply_rock(plane, plan['plan_id'], approval['approval_decision_id'], client, definition_fingerprint=definition)
