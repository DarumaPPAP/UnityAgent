import copy
import json
from pathlib import Path
import unittest
from tools.subagent_source_paths import resolve_source_paths


class SourceLockLayoutTests(unittest.TestCase):
    def test_current_artist_sources_use_the_same_checkout_without_a_host(self):
        lock = json.loads((Path(__file__).resolve().parents[2] / 'src/unityagent/runtime/distribution/subagent-sources.lock.json').read_text(encoding='utf-8'))
        paths = resolve_source_paths(lock)
        self.assertEqual(paths['source_mode'], 'same_checkout')
        self.assertEqual(paths['artist_provider'], 'unity_cli')
        self.assertEqual(paths['artist_package'], 'subagent/artist_subagent/tools/editor')
        self.assertNotIn('artist_cli_project', paths)

    def lock(self, layout, cli):
        return {'hub': {'repository': 'DarumaPPAP/UnitySubAgentHub', 'commit': 'a'*40, 'snapshot_exporter': layout+'/export_snapshot.py' if layout.startswith('Hub') else layout+'/export_agent_snapshot.py', 'registry': 'Hub/Registry/subagents.yaml' if layout.startswith('Hub') else 'Registry/subagents.yaml'}, 'specialist_sources': {'artist_subagent': {'manifest': 'Hub/SubAgents/artist_subagent/manifest.yaml' if layout.startswith('Hub') else 'SubAgents/artist_subagent/manifest.yaml', 'backend_package': 'Packages/com.darumappap.artist-subagent', 'backend_cli_project': cli+'/UnityArtist.Cli.csproj'}}}

    def test_historical_host_layouts_are_not_current_execution_sources(self):
        for layout in ('Tests/Hub', 'Hub/Tools'):
            for cli in ('src/UnityArtist.Cli', 'cli/artist'):
                with self.subTest(layout=layout,cli=cli):
                    with self.assertRaises(ValueError):
                        resolve_source_paths(self.lock(layout,cli))

    def test_unknown_sources_or_mixed_catalog_layout_fail_closed(self):
        base=self.lock('Hub/Tools','src/UnityArtist.Cli')
        for obj,key,value in (('hub','commit','main'),('hub','repository','Other/Hub'),('hub','snapshot_exporter','../export.py'),('hub','registry','Registry/subagents.yaml'),('artist','backend_cli_project','../Unknown.csproj'),('artist','manifest','Hub/SubAgents/imposter_subagent/manifest.yaml')):
            item=copy.deepcopy(base)
            target=item['hub'] if obj=='hub' else item['specialist_sources']['artist_subagent']
            target[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): resolve_source_paths(item)
