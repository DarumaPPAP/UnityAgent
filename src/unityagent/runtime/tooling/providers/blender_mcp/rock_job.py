"""Session/JobをTaskに拘束し、曖昧な生成Timeoutを自動再送しない。"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib

from unityagent.persistence.store.atomic_store import safe_id, sha256_json, read_json, atomic_write_json, exclusive_file_lock
from .rock_template import rock_template


class RockJob:
    def __init__(self, state_root, client, *, check_approval):
        self.root = Path(state_root).resolve()
        self.client = client
        self.check_approval = check_approval

    def run(self, job_id, *, approval_ref):
        if not approval_ref:
            raise ValueError('Blender scene mutation requires Approval')
        folder = self.root / 'blender-jobs' / safe_id(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        output, artifact_manifest = folder / 'Rock.fbx', folder / 'artifact.json'
        code = rock_template(output, artifact_manifest)
        digest = sha256_json({'template': code, 'approval_ref': approval_ref})
        state_path = folder / 'job.json'
        # Unity Project Leaseは取得しない。Blender Sessionだけを排他する。
        with exclusive_file_lock(self.root / 'blender-sessions' / (safe_id(self.client.session_id) + '.lock')):
            if state_path.exists():
                state = read_json(state_path)
                if state['request_digest'] != digest or state['session_id'] != self.client.session_id:
                    raise ValueError('Blender Job request or Session changed; reconcile before resume')
                return state
            self.check_approval(digest)
            state = {'schema_version': '1.0', 'job_id': job_id, 'session_id': self.client.session_id,
                     'approval_ref': approval_ref, 'request_digest': digest, 'status': 'submitted',
                     'submitted_at': datetime.now(timezone.utc).isoformat(),
                     'artifact_path': str(output), 'token_usage': 'unmeasured'}
            atomic_write_json(state_path, state)
            try:
                result = self.client.tool('execute_blender_code', {'code': code})
                state['mcp_result'] = result
                artifact = read_json(artifact_manifest)
                measured_hash = hashlib.sha256(output.read_bytes()).hexdigest()
                if artifact['sha256'] != measured_hash or artifact['vertices'] <= 0 or artifact['triangles'] <= 0:
                    raise ValueError('Artifact hash or geometry is invalid')
                if artifact['scale'] != [1, 1, 1] or artifact['texture_dependencies'] or artifact['uv_layers'] < 1:
                    raise ValueError('Artifact scale, UV or texture dependency is invalid')
                state.update(status='completed', artifact=artifact, artifact_hash=measured_hash)
            except (TimeoutError, OSError) as exc:
                state.update(status='uncertain', reason=str(exc))
            except (ValueError, KeyError, RuntimeError) as exc:
                state.update(status='failed', reason=str(exc))
            from unityagent.persistence.store.atomic_store import PersistenceError
            atomic_write_json(state_path, state)
            return state
