"""UPM内包P9 FixtureはUnityAgent正本とGit blobが一致し、Hub取得不要。"""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITOR = ROOT / "Packages/com.darumappap.unity-agent/Editor"
SOURCE = EDITOR / "Verification~"
MANIFEST = SOURCE / "p9-source-manifest.json"

def tracked_sources():
    paths = [x for x in ROOT.glob("tests/unity/projects/**/*") if x.is_file()]
    paths += [x for x in ROOT.glob("tests/unity/verify/**/*") if x.is_file()]
    paths += [x for x in ROOT.glob("tests/unity/scripts/**/*") if x.is_file()]
    paths += [ROOT / "tests/unity/matrix.yaml"]
    paths += [x for x in ROOT.glob("subagent/artist_subagent/tools/editor/**/*") if x.is_file()]
    paths += [x for x in ROOT.glob("tests/unity/editor/artist/**/*") if x.is_file()]
    return {x.relative_to(ROOT).as_posix(): x for x in paths}


def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class EditorBundledVerificationTests(unittest.TestCase):
    def test_manifest_and_sources_match_bitwise(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "unityagent_embedded_p9_sources")
        files = {row["path"]: row for row in payload["files"]}
        tracked = tracked_sources()
        self.assertEqual(set(files), set(tracked))
        mirrored = {x.relative_to(SOURCE).as_posix() for x in SOURCE.rglob("*")
                    if x.is_file() and x != MANIFEST}
        self.assertEqual(set(files), mirrored)
        for relative, path in tracked.items():
            with self.subTest(path=relative):
                original = path.read_bytes()
                self.assertEqual((SOURCE / relative).read_bytes(), original)
                self.assertEqual(files[relative]["size"], len(original))
                self.assertEqual(files[relative]["sha1"], blob_hash(original))

    def test_source_is_self_contained(self):
        class_text = (EDITOR / "VerificationFixtureSource.cs").read_text(encoding="utf-8")
        panel = (EDITOR / "SetupVerificationPanel.cs").read_text(encoding="utf-8")
        self.assertIn("p9-source-manifest.json", class_text)
        self.assertIn("GitObjectHash", class_text)
        self.assertIn("ContainsLinkBetween", class_text)
        self.assertIn("TryGetVerifiedSource", panel)
        self.assertIn('PYTHONDONTWRITEBYTECODE', panel)
        self.assertNotIn('VerificationHubSource', panel)
        self.assertNotIn('s_hubRoot', panel)
        self.assertNotIn('GitRemote', class_text)
        self.assertNotIn('OpenFolderPanel', panel)
        self.assertTrue((EDITOR / "VerificationFixtureSource.cs.meta").is_file())

if __name__ == "__main__":
    unittest.main()
