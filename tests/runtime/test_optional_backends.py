import tempfile
import unittest
from pathlib import Path
from unityagent.runtime.tooling.providers.installer.installer_provider import InstallerProvider
from unityagent.runtime.contracts.toolchain_setup_contract import validate_toolchain_setup_request


class OptionalBackendTests(unittest.TestCase):
    def test_missing_optional_tools_do_not_fail_doctor_or_install_automatically(self):
        with tempfile.TemporaryDirectory() as root:
            provider = InstallerProvider(root, which_fn=lambda _: None)
            request = {'schema_version': '1.0', 'request_id': 'optional', 'entry_point': 'codex_plugin', 'operation': 'doctor',
                       'project_root': root, 'products': ['blender_mcp', 'unity_cli_loop'],
                       'channel': '0.0.8-beta', 'non_interactive': True, 'approval_ref': None,
                       'expected_plan_id': None, 'install_root': None, 'codex_cli_path': None}
            validate_toolchain_setup_request(request)
            result = provider.doctor(request)
            self.assertEqual(result['status'], 'passed')
            self.assertEqual([e['status'] for e in result['entries']], ['unavailable', 'unavailable'])
            request['operation'] = 'plan'
            plan = provider.plan(request)
            self.assertEqual(plan['status'], 'unavailable')
            self.assertTrue(all(a['action'] == 'manual_required' for a in plan['actions']))
