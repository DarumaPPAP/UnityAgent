"""旧Artist BackendをProductionへ戻さない撤去Gate。移行済み旧経路の再混入を防止する。"""
import ast
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ArtistRetirementTests(unittest.TestCase):
    def test_retired_provider_and_standalone_host_sources_are_absent(self):
        for relative in ("src/unityagent/runtime/tooling/providers/unity_artist_cli", "subagent/artist_subagent/tools/host", "subagent/artist_subagent/tools/editor/Editor/Batch", "tests/unity/projects/historical/2022.3", "tests/subagent/artist/tools"):
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())

    def test_retired_snapshot_and_receipt_are_not_accepted(self):
        snapshot = (ROOT / "src/unityagent/runtime/contracts/environment-snapshot.schema.yaml").read_text(encoding="utf-8")
        receipt = (ROOT / "src/unityagent/runtime/contracts/install-receipt.schema.yaml").read_text(encoding="utf-8")
        self.assertNotIn("  unity_artist_cli:", snapshot)
        self.assertNotIn("artist_subagent, unity_artist_cli", receipt)

    def test_production_python_has_no_retired_provider_import(self):
        for path in (ROOT / "src/unityagent").rglob("*.py"):
            if "_resources" in path.parts or "__pycache__" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [node.module or ""] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names] if isinstance(node, ast.Import) else []
                self.assertFalse(any("providers.unity_artist_cli" in name for name in names), str(path))

    def test_release_and_setup_do_not_install_or_distribute_the_host(self):
        setup = yaml.safe_load((ROOT / "src/unityagent/runtime/contracts/toolchain-setup-request.schema.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("unity_artist_cli", str(setup))
        for relative in (".github/workflows/release-tag.yml", ".github/workflows/validate-agent-contracts.yml", "setup.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("tools/host", source)
            self.assertNotIn("UnityArtist.Tools.csproj", source)
