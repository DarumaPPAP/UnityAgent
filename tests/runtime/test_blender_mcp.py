import tempfile
import unittest
from pathlib import Path
from unityagent.runtime.tooling.providers.blender_mcp.rock_job import RockJob


class Client:
    session_id = 'session-1'
    blender_session_identity = 'fixture-observed-session-1'
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
        self.job = RockJob(self.root, self.client, check_approval=lambda digest: None, session_lock_root=self.root/'session-locks')

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
        self.assertNotIn('import hashlib', code)
        self.assertNotIn('open(', code)
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
                (folder/'Rock.fbx').write_bytes(b'Kaydara FBX Binary  \x00\x1a\x00'+b'fixture-only-not-real-geometry'*80)
                return {'content':[{'type':'text','text':'Code executed successfully: UNITYAGENT_ROCK_V1:'+
                    json.dumps({'schema_version':'1.0','object_name':'UnityAgentRock',
                    'vertices':42,'triangles':80,'scale':[1,1,1],'uv_layers':1,
                    'dimensions':[1.0,1.0,1.0],'texture_dependencies':[]})}]}
            client.tool = create_fixture
            plane = UnityAgentControlPlane(state)
            client.blender_session_identity = None
            blocked = apply_rock(plane, plan['plan_id'], approval['approval_decision_id'], client, definition_fingerprint=definition)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertFalse((state/'blender-jobs/fixture-rock/job.json').exists())
            client.blender_session_identity = 'fixture-observed-session-1'
            with patch('unityagent.runtime.dispatcher.tool_runtime_dispatcher.RuntimeProjectLease', side_effect=AssertionError('Unity Lease held during Blender')):
                result = apply_rock(plane, plan['plan_id'], approval['approval_decision_id'], client, definition_fingerprint=definition)
            self.assertEqual(result['status'], 'completed', result)
            produced = json.loads((state/'blender-jobs/fixture-rock/artifact.json').read_text())
            self.assertEqual(produced['sha256'], hashlib.sha256((state/'blender-jobs/fixture-rock/Rock.fbx').read_bytes()).hexdigest())
            self.assertEqual(len(result['evidence_refs']), 1)
            self.assertFalse(result['verified'])
            self.assertEqual(result['unity_import'], 'BLOCKED_NOT_RUN')
            ApprovalDecisionStore(state).revoke(approval['approval_decision_id'])
            with self.assertRaisesRegex(ValueError, 'revoked'):
                apply_rock(plane, plan['plan_id'], approval['approval_decision_id'], client, definition_fingerprint=definition)


class McpTransportTests(unittest.TestCase):
    def test_real_stdio_handshake_and_allowlisted_tool_call(self):
        import sys
        from unityagent.runtime.tooling.providers.blender_mcp.stdio_client import McpStdioClient
        with tempfile.TemporaryDirectory() as directory:
            server=Path(directory)/'fixture_mcp.py'
            server.write_text('''import json, sys
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    method=request['method']
    if method=='initialize': result={'protocolVersion':'2024-11-05','serverInfo':{'name':'fixture','version':'1'}}
    elif method=='tools/list': result={'tools':[{'name':'get_scene_info'},{'name':'execute_blender_code'}]}
    else: result={'content':[{'type':'text','text':'fixture scene observation'}]}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
''')
            with McpStdioClient([sys.executable,'-u',str(server)]) as client:
                self.assertEqual(client.identity['serverInfo']['name'],'fixture')
                self.assertIsNone(client.blender_session_identity)
                self.assertTrue(client.tool('get_scene_info',{})['content'])
                with self.assertRaises(ValueError): client.tool('arbitrary_python',{})
            self.assertIsNotNone(client.process.poll())


    def test_observed_session_excludes_different_persistence_roots(self):
        import threading
        import uuid
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            started1,started2,release=threading.Event(),threading.Event(),threading.Event()
            first,second=Client(),Client()
            first.session_id=second.session_id='fixture-'+uuid.uuid4().hex
            def tool1(*args):
                started1.set()
                if not release.wait(3): raise TimeoutError('fixture synchronization failed')
                return {'content':[]}
            def tool2(*args):
                started2.set()
                return {'content':[]}
            first.tool,second.tool=tool1,tool2
            job1=RockJob(root/'state1',first,check_approval=lambda _:None)
            job2=RockJob(root/'state2',second,check_approval=lambda _:None)
            t1=threading.Thread(target=lambda:job1.run('a',approval_ref='a'))
            t2=threading.Thread(target=lambda:job2.run('b',approval_ref='b'))
            try:
                t1.start()
                self.assertTrue(started1.wait(2))
                t2.start()
                self.assertFalse(started2.wait(0.1))
            finally:
                release.set()
                t1.join(3)
                if t2.ident is not None: t2.join(3)
            self.assertTrue(started2.is_set())
            self.assertFalse(t1.is_alive() or t2.is_alive())
