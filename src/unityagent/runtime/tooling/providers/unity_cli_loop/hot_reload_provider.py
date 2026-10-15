"""承認済みSourceを固定Runnerで適用し、部分適用を成功へ昇格しない。"""
from pathlib import Path
import hashlib
import json
import subprocess

from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.sandbox.workspace_guard import confined_path
from unityagent.persistence.store.atomic_store import sha256_json


def validate_hot_reload_result(result):
    if (result.get('Success') is not True or result.get('Outcome') != 'Applied'
            or result.get('SkippedTotal') != 0 or result.get('FailedTotal') != 0
            or not isinstance(result.get('PatchedTotal'), int) or result['PatchedTotal'] <= 0):
        raise ValueError('Hot Reload failed, skipped, partial, empty or replaced by compile')
    methods = result.get('Methods')
    if not isinstance(methods, list) or not methods:
        raise ValueError('Hot Reload method results are missing')
    for row in methods + result.get('IntroducedTypes', []):
        if row.get('Kind') not in {'Patched', 'Added', 'AlreadyActive', 'Unchanged'}:
            raise ValueError('Hot Reload contains skipped or failed changes')


class HotReloadProvider:
    def __init__(self, project_root, runner_path, *, binary_sha256, check_approval, command_runner=subprocess.run):
        self.project = Path(project_root).resolve(strict=True)
        self.runner = Path(runner_path).resolve(strict=True)
        if self.runner.name.lower() not in {'uloop-project-runner', 'uloop-project-runner.exe'}:
            raise ValueError('Use a reviewed local project runner; dispatcher may download/update automatically')
        self.binary_hash = binary_sha256
        self.check_approval = check_approval
        self.command_runner = command_runner

    def _command(self, *arguments):
        # Dispatcherを経由せず、レビュー済みの既存Binaryだけを使用する。
        result = self.command_runner([str(self.runner), *arguments, '--project-path', str(self.project)],
            cwd=self.project, capture_output=True, text=True, encoding='utf-8', timeout=120, check=False)
        if result.returncode != 0:
            raise ValueError('CLI Loop command failed: ' + result.stderr[:1000])
        return json.loads(result.stdout)

    def execute(self, request, context, arguments):
        try:
            validate_capability_request(request)
            if request['capability'] != 'editor.hot_reload' or Path(request['project_root']).resolve() != self.project:
                raise ValueError('Hot Reload Project or capability mismatch')
            if not context.policy_allowed or context.approval_complete is not True or not request['approval_ref']:
                raise ValueError('Hot Reload requires approved Source and execution scope')
            hashes = arguments.get('source_hashes')
            scope = request['mutation_scope']
            if not isinstance(hashes, dict) or not hashes or set(hashes) != set(scope['allowed_paths']):
                raise ValueError('Exact Source hashes and Mutation Scope are required')
            for name, expected in hashes.items():
                if not name.startswith('Assets/') or not name.endswith('.cs') or any(c in name for c in ',\r\n'):
                    raise ValueError('Only explicit confined C# Source files are allowed')
                source = confined_path(self.project, name, require_file=True)
                if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    raise ValueError('Source revision changed before Hot Reload')
                if any(name == path or name.startswith(path.rstrip('/')+'/') for path in scope['prohibited_paths']):
                    raise ValueError('Source is prohibited by Mutation Scope')
            if hashlib.sha256(self.runner.read_bytes()).hexdigest() != self.binary_hash:
                raise ValueError('Reviewed CLI Loop runner revision changed')
            self.check_approval(sha256_json({'request':request,'source_hashes':hashes,'binary_hash':self.binary_hash}))
            status = self._command('status')
            if status.get('Ready') is not True or status.get('State') != 'Ready' or status.get('IsPlaying') is not True:
                raise ValueError('Bound Editor is not ready in Play Mode')
            result = self._command('hot-reload', '--files', ','.join(sorted(hashes)), '--compile-on-skip', 'off')
            validate_hot_reload_result(result)
            for name, expected in hashes.items():
                if hashlib.sha256(confined_path(self.project,name,require_file=True).read_bytes()).hexdigest() != expected:
                    raise ValueError('Source revision changed during Hot Reload; reconcile runtime effects')
            return {'status':'passed','provider_ref':'unity_cli_loop', 'failure_class':None,
                    'evidence':['editor_observation','mutation_evidence'], 'hot_reload':result,
                    'normal_compile':'not_observed','play_behavior':'not_observed',
                    'source_hashes':hashes, 'runner_sha256':self.binary_hash,
                    'runtime_rollback':'not_supported; source restore does not undo runtime side effects'}
        except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            return {'status':'failed','provider_ref':'unity_cli_loop','failure_class':'not_observed',
                    'evidence':[], 'reason':str(exc), 'normal_compile':'not_observed'}
