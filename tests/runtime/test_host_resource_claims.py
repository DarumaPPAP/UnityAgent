from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from unityagent.runtime.guardrails.project_lease import ProjectLeaseBusy


class HostResourceClaimsTests(unittest.TestCase):
    def test_claim_is_exclusive_and_released_without_ttl_or_retry(self):
        from unityagent.runtime.guardrails.project_lease import acquire_host_claims
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with acquire_host_claims(['host:compiler-cache'], owner='first', lock_root=directory):
                with self.assertRaises(ProjectLeaseBusy):
                    with acquire_host_claims(['host:compiler-cache'], owner='second', lock_root=directory):
                        self.fail('conflicting claim entered')
                with acquire_host_claims(['host:other'], owner='other', lock_root=directory):
                    pass
            with acquire_host_claims(['host:compiler-cache'], owner='after', lock_root=directory):
                pass

    def test_claim_order_is_canonical_and_aliases_cannot_split_the_lock(self):
        from unityagent.runtime.guardrails.project_lease import acquire_host_claims
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with acquire_host_claims(['HOST:Z', 'host:a'], owner='first', lock_root=directory) as records:
                self.assertEqual([item['resource_identity'] for item in records], ['host:a', 'host:z'])
                with self.assertRaises(ProjectLeaseBusy):
                    with acquire_host_claims(['host:z'], owner='other', lock_root=directory):
                        pass

    def test_partial_acquisition_failure_releases_earlier_claims(self):
        from unityagent.runtime.guardrails.project_lease import acquire_host_claims
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with acquire_host_claims(['host:z'], owner='first', lock_root=directory):
                with self.assertRaises(ProjectLeaseBusy):
                    with acquire_host_claims(['host:a', 'host:z'], owner='blocked', lock_root=directory):
                        pass
                with acquire_host_claims(['host:a'], owner='after', lock_root=directory):
                    pass


class HostClaimControlPlaneTests(unittest.TestCase):
    from tests.orchestration.test_task_execution import TaskDagTests
    setUp = TaskDagTests.setUp

    def test_host_conflict_releases_project_run_lock_before_returning_blocked(self):
        from unityagent.runtime.guardrails.project_lease import acquire_host_claims, acquire_project_lease
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        entry = {'schema_version': '2.0', 'request_id': 'claim-conflict', 'entry_point': 'codex_plugin',
                 'project_root': str(self.project), 'intent': {'kind': 'project_inspection'}}
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            with acquire_host_claims(['host:shared'], owner='other'):
                result = self.plane.execute(entry, run_id='host-conflict', environment_snapshot=self.snapshot,
                    context=ResolutionContext(policy_allowed=True), executors={'file': self.provider.execute},
                    definition_fingerprint=self.definition, _host_resource_claims=['host:shared'])
                self.assertEqual(result['status'], 'blocked')
                with acquire_project_lease(self.project, owner='after-block'):
                    pass

    def test_host_acquisition_interrupt_releases_project_even_with_retained_traceback(self):
        import sys
        from unityagent.runtime.guardrails.project_lease import acquire_project_lease
        from unityagent.runtime.tooling.capability_resolver import ResolutionContext
        entry = {'schema_version': '2.0', 'request_id': 'claim-interrupt', 'entry_point': 'codex_plugin',
                 'project_root': str(self.project), 'intent': {'kind': 'project_inspection'}}
        with patch('unityagent.runtime.guardrails.project_lease._default_lock_root', return_value=self.root / 'locks'):
            with patch('unityagent.runtime.guardrails.project_lease.acquire_host_claims', side_effect=KeyboardInterrupt):
                try:
                    self.plane.execute(entry, environment_snapshot=self.snapshot,
                        context=ResolutionContext(policy_allowed=True), executors={'file': self.provider.execute},
                        definition_fingerprint=self.definition, _host_resource_claims=['host:shared'])
                except KeyboardInterrupt:
                    retained = sys.exc_info()
                else:
                    self.fail('interrupt not raised')
            with acquire_project_lease(self.project, owner='after-interrupt'):
                pass
