import copy
import unittest
from tools.subagent_source_paths import resolve_source_paths


class SourceLockLayoutTests(unittest.TestCase):
    def lock(self, layout, cli):
        return {'hub': {'repository': 'DarumaPPAP/UnitySubAgentHub', 'commit': 'a'*40, 'snapshot_exporter': layout+'/export_snapshot.py' if layout.startswith('Hub') else layout+'/export_agent_snapshot.py', 'registry': 'Hub/Registry/subagents.yaml' if layout.startswith('Hub') else 'Registry/subagents.yaml'}, 'specialist_sources': {'artist_subagent': {'manifest': 'Hub/SubAgents/artist_subagent/manifest.yaml' if layout.startswith('Hub') else 'SubAgents/artist_subagent/manifest.yaml', 'backend_package': 'Packages/com.darumappap.artist-subagent', 'backend_cli_project': cli+'/UnityArtist.Cli.csproj'}}}

    def test_catalog_and_artist_transitions_resolve_known_paths(self):
        for layout in ('Tests/Hub', 'Hub/Tools'):
            for cli in ('src/UnityArtist.Cli', 'cli/artist'):
                with self.subTest(layout=layout,cli=cli):
                    paths = resolve_source_paths(self.lock(layout,cli))
                    self.assertEqual(paths['artist_cli_project'],cli+'/UnityArtist.Cli.csproj')
                    self.assertEqual(paths['hub_tests'],'Hub/Tests' if layout.startswith('Hub') else 'Tests/Hub')
                    self.assertEqual(paths['artist_contract_verifier'],'ci/verify/verify_artist_backend_contract.py' if cli=='cli/artist' else 'Tests/Backend/verify_artist_backend_contract.py')

    def test_unknown_sources_or_mixed_catalog_layout_fail_closed(self):
        base=self.lock('Hub/Tools','src/UnityArtist.Cli')
        for obj,key,value in (('hub','commit','main'),('hub','repository','Other/Hub'),('hub','snapshot_exporter','../export.py'),('hub','registry','Registry/subagents.yaml'),('artist','backend_cli_project','../Unknown.csproj'),('artist','manifest','Hub/SubAgents/imposter_subagent/manifest.yaml')):
            item=copy.deepcopy(base)
            target=item['hub'] if obj=='hub' else item['specialist_sources']['artist_subagent']
            target[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): resolve_source_paths(item)
