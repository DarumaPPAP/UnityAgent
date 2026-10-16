"""G1 Unity環境を偽装しないHost契約・拒否テスト。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from unityagent.control_plane.rock_import import (
    plan_rock_import, approve_rock_import, _check_approval,
)
from unityagent.runtime.tooling.providers.native_unity_editor.rock_import_provider import (
    _verify_receipt, RockImportProvider, TARGET, MODEL,
)
from unityagent.runtime.tooling.providers.native_unity_editor.process_builder import (
    build_execute_method_command,
)


class RockImportContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'Project'
        self.state = self.root / 'state'
        for part in ('Assets','Packages','ProjectSettings'):
            (self.project/part).mkdir(parents=True)
        (self.project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.12f1\n')
        (self.project/'Packages/manifest.json').write_text('{"dependencies":{}}')
        self.job = self.state / 'blender-jobs' / 'rock-g1'
        self.job.mkdir(parents=True)
        self.artifact = self.job/'Rock.fbx'
        self.artifact.write_bytes(b'Kaydara FBX Binary  \x00\x1a\x00'+ b'fixed-fbx-fixture'*100)
        digest=hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        (self.job/'artifact.json').write_text(json.dumps({'sha256':digest,'uv_layers':1}))
        (self.job/'job.json').write_text(json.dumps({'status':'completed','artifact_hash':digest}))
        self.definition={'schema_version':'1.0','architecture_version':'fixture'}

    def test_plan_requires_integrity_and_create_only_destination(self):
        plan=plan_rock_import(self.project,self.state,'rock-g1',self.definition)
        self.assertEqual(plan['source_sha256'],hashlib.sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual(plan['target_root'],TARGET)
        self.assertIn(TARGET+'.meta',plan['owned_files'])
        (self.project/TARGET).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError,'target'):
            plan_rock_import(self.project,self.state,'rock-g1',self.definition)

    def test_import_and_save_require_distinct_revocable_approvals(self):
        plan=plan_rock_import(self.project,self.state,'rock-g1',self.definition)
        mutation=approve_rock_import(self.state,plan['plan_id'],'mutation')
        save=approve_rock_import(self.state,plan['plan_id'],'save')
        _check_approval(self.state,plan,mutation['approval_decision_id'],'mutation')
        _check_approval(self.state,plan,save['approval_decision_id'],'save')
        with self.assertRaisesRegex(ValueError,'invalid'):
            _check_approval(self.state,plan,mutation['approval_decision_id'],'save')
        from unityagent.persistence.approval.approval_store import ApprovalDecisionStore
        ApprovalDecisionStore(self.state).revoke(mutation['approval_decision_id'])
        with self.assertRaisesRegex(ValueError,'revoked'):
            _check_approval(self.state,plan,mutation['approval_decision_id'],'mutation')

    def test_receipt_absent_cannot_pass(self):
        with self.assertRaises(OSError):
            _verify_receipt(self.project,self.state/'missing-receipt.json',
                            hashlib.sha256(self.artifact.read_bytes()).hexdigest())

    def test_unapproved_editor_bridge_method_rejected(self):
        from unityagent.runtime.tooling.providers.native_unity_editor.process_builder import REPOSITORY_EXECUTE_METHOD_ALLOWLIST
        self.assertEqual(REPOSITORY_EXECUTE_METHOD_ALLOWLIST,{
            "DarumaPPAP.UnityAgent.Editor.RockImportBridge.ApplyApproved",
            "DarumaPPAP.UnityAgent.Editor.RockImportBridge.RollbackApproved",
        })
        with self.assertRaisesRegex(ValueError,'not repository-allowlisted'):
            build_execute_method_command(executable_path=Path('/editor'),project_root=self.project,
                log_path=self.root/'run.log',method_name="UnityAgent.UnsafeEval")

    def test_failed_editor_preflight_never_claims_import_completion(self):
        plan=plan_rock_import(self.project,self.state,'rock-g1',self.definition)
        mutation=approve_rock_import(self.state,plan['plan_id'],'mutation')
        save=approve_rock_import(self.state,plan['plan_id'],'save')
        approvals={'mutation':mutation['approval_decision_id'],'save':save['approval_decision_id']}
        def checks(_plan,_action):
            _check_approval(self.state,plan,approvals['mutation'],'mutation')
            _check_approval(self.state,plan,approvals['save'],'save')
        class MissingEditor:
            def __init__(self,*a,**k): pass
            def _safe_mode_failure(self): return {'status':'failed','reason':'no Unity Editor'}
            def _check_editor_conflict(self): return None
        provider=RockImportProvider(self.project,self.state,snapshot={},check_approvals=checks,
                                    editor_factory=MissingEditor)
        request={'schema_version':'1.0','capability':'scene.mutate','operation_kind':'editor_mutation',
                 'project_root':str(self.project),'mutation_scope':plan['mutation_scope'],
                 'approval_ref':approvals['mutation'],'required_evidence':['editor_observation','mutation_evidence'],
                 'preferred_surface':'editor','qualifiers':{'workflow':'blender_rock_import'}}
        class Context:
            policy_allowed=True
            approval_complete=True
        result=provider.execute(request,Context(),{'plan':plan,'action':'apply',
                         'approval_ref':approvals['mutation'],'approvals':approvals})
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['evidence'],[])
        self.assertEqual(result['external_effects'],'reconciliation_required')
        self.assertFalse((self.state/'rock-import'/plan['plan_id']/'receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
