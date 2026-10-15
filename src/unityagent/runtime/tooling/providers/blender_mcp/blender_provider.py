"""Runtime Broker向けの固定岩制作。ProviderはApprovalとTask所有権を決定しない。"""
from pathlib import Path
from unityagent.runtime.contracts.capability_contract import validate_capability_request
from .rock_job import RockJob


class BlenderProvider:
    def __init__(self, project_root, state_root, client, *, job_id, check_approval):
        self.project = str(Path(project_root).resolve())
        self.job = RockJob(state_root, client, check_approval=check_approval)
        self.job_id = job_id

    def execute(self, request, context, arguments):
        validate_capability_request(request)
        scope = {'allowed_paths': ['blender-jobs/' + self.job_id], 'prohibited_paths': ['Assets', 'Packages', 'ProjectSettings']}
        if (request['capability'] != 'world.create' or request.get('qualifiers') != {'workflow': 'blender_rock'}
                or str(Path(request['project_root']).resolve()) != self.project or request['mutation_scope'] != scope):
            return {'status': 'failed', 'failure_class': 'scope_violation', 'evidence': []}
        if not context.policy_allowed or context.approval_complete is not True:
            return {'status': 'failed', 'failure_class': 'blocked_by_approval', 'evidence': []}
        result = self.job.run(self.job_id, approval_ref=request['approval_ref'])
        passed = result['status'] == 'completed'
        return {'status': 'passed' if passed else 'failed', 'provider_ref': 'blender_mcp',
                'failure_class': None if passed else 'not_observed', 'job': result,
                'evidence': ['domain_result', 'mutation_evidence'] if passed else [],
                'artifact_path': result.get('artifact_path'), 'artifact_hash': result.get('artifact_hash')}
