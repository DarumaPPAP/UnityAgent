"""The P9 release boundary must reject synthetic, stale or blocked evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/release"))
from verify_p9_evidence import verify

SHA = "a" * 40
REPO = "example/private-p9"
RUN = 12345


class P9GateTests(unittest.TestCase):
    def make_run(self, root):
        source = Path(root)
        data = {
            "editor.log": "Unity completed",
            "results.xml": '<test-run result="Passed" total="1" passed="1" failed="0"><test-case result="Passed"/></test-run>',
            "packages-lock.json": json.dumps({"dependencies":{"com.unity.render-pipelines.universal":{"version":"17.3.0"}}}),
            "pipeline-smoke.png": b"\x89PNG\r\n\x1a\n" + b"capture",
            "graphics-device.json": json.dumps({"editorVersion":"6000.3.12f1","deviceType":"Direct3D11","pixelVariation":1}),
            "editor-version.txt": "6000.3.12f1"
        }
        for name, value in data.items():
            (source / name).write_bytes(value if isinstance(value, bytes) else value.encode())
        evidence = {
            "status":"PASS","observation":"observed","fixture":"p9-lts-urp","pipeline":"urp",
            "requested_editor":"6000.3.12f1","observed_editor":"6000.3.12f1",
            "editor_test_process_started":True,"source_changed_during_execution":False,
            "run_id":str(RUN),"source_identity":{"commit":SHA},"tests_passed":1,
            "graphics_observation":{"editorVersion":"6000.3.12f1","deviceType":"Direct3D11","pixelVariation":1},
            "resolved_packages":{"com.unity.render-pipelines.universal":{"version":"17.3.0"}},
            "artifact_hashes":{n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in data}
        }
        (source/"evidence.json").write_text(json.dumps(evidence))
        run={"id":RUN,"repository":{"full_name":REPO},"name":"UnityAgent P9 Release Verification",
             "event":"workflow_dispatch","head_branch":"main","status":"completed","conclusion":"success",
             "path":REPO+"/.github/workflows/p9-release-verification.yml@refs/heads/main"}
        return run, evidence
    def test_valid_measured_p9_passes_without_g1(self):
        with tempfile.TemporaryDirectory() as root:
            run,_=self.make_run(root)
            result=verify(Path(root),run,SHA,REPO,RUN)
            self.assertEqual(result["status"],"P9_EDITOR_VERIFIED")
            self.assertEqual(result["g1_status"],"BLOCKED_NOT_RUN")
    def test_gates_refuse_forged_or_stale_evidence(self):
        for change in ("wrong_sha","wrong_run","blocked","fake_graphics","bad_hash","wrong_workflow","wrong_lock","partial_test"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                run,evidence=self.make_run(root)
                if change=="wrong_sha": evidence["source_identity"]["commit"]="b"*40
                elif change=="wrong_run": evidence["run_id"]="456"
                elif change=="blocked": evidence["status"]="BLOCKED_NOT_RUN"
                elif change=="fake_graphics": evidence["graphics_observation"]["deviceType"]="Null"
                elif change=="bad_hash": evidence["artifact_hashes"]["pipeline-smoke.png"]="0"*64
                elif change=="wrong_workflow": run["path"]="evil.yml"
                elif change=="wrong_lock": (Path(root)/"packages-lock.json").write_text('{"dependencies":{}}')
                elif change=="partial_test": evidence["tests_passed"]=2
                (Path(root)/"evidence.json").write_text(json.dumps(evidence))
                with self.assertRaises(ValueError):
                    verify(Path(root),run,SHA,REPO,RUN)


if __name__ == "__main__":
    unittest.main()
