"""PR品質の正常系、形式エラー、Evidence警告の回帰テスト。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from validate_pr import validate

BODY = """<!-- pr-type: feature -->
<!-- evidence: none -->
<!-- evidence-status: none -->

## 概要・変更目的
既存CLIでは操作が不足するため機能を増やす。

## 主な変更内容
明示的に承認された新しいCLI操作を追加した。

## 検証結果・Evidence
Host Unit Testを実行し成功、Head SHAを確認した。

## 未検証・既知のリスク
実Unity G1の結果はBLOCKED_NOT_RUN、専用Runnerで再検証する。

## 関連Issue・PR・影響範囲
CLI機能のみに影響し、関連Issueは存在しない。
"""
def check(body=BODY,title="機能追加：明示的なCLI操作を追加"):return validate(title,body)
class PRQualityTests(unittest.TestCase):
    def test_valid_feature(self):self.assertEqual(check(),([],[]))
    def test_no_type(self):self.assertTrue(check(BODY.replace("<!-- pr-type: feature -->",""))[0])
    def test_duplicate_type(self):self.assertTrue(check(BODY.replace("<!-- pr-type: feature -->","<!-- pr-type: feature -->\n<!-- pr-type: fix -->"))[0])
    def test_wrong_title(self):self.assertTrue(check(title="feat: tiny patch")[0])
    def test_missing_heading(self):self.assertTrue(check(BODY.replace("## 未検証・既知のリスク","## Unknown"))[0])
    def test_placeholder(self):self.assertTrue(check(BODY.replace("明示的に承認された新しいCLI操作を追加した。","TODO"))[0])
    def test_fenced_fake_heading(self):
        text=BODY.replace("## 関連Issue・PR・影響範囲\nCLI機能のみに影響し、関連Issueは存在しない。","")
        text+="\n~~~markdown\n## 関連Issue・PR・影響範囲\n偽の内容\n~~~\n"
        self.assertTrue(check(text)[0])
    def test_qa_does_not_require_perf(self):
        body=BODY.replace("pr-type: feature","pr-type: qa")
        self.assertEqual(check(body,"テスト整備：不具合再現テストを追加"),([],[]))
    def test_perf_without_measurement_warns(self):
        body=BODY.replace("pr-type: feature","pr-type: performance").replace("evidence: none","evidence: performance").replace("evidence-status: none","evidence-status: performance=blocked_not_run")
        error,warn=check(body,"性能改善：描画処理負荷を削減")
        self.assertFalse(error);self.assertTrue(warn)
    def test_perf_claimed_pass_without_data_fails(self):
        body=BODY.replace("pr-type: feature","pr-type: performance").replace("evidence: none","evidence: performance").replace("evidence-status: none","evidence-status: performance=passed")
        self.assertTrue(check(body,"性能改善：描画処理負荷を削減")[0])
    def test_visual_without_image_warns(self):
        body=BODY.replace("pr-type: feature","pr-type: visual").replace("evidence: none","evidence: visual").replace("evidence-status: none","evidence-status: visual=not_observed")
        error,warn=check(body,"表示変更：画面の配置を改善")
        self.assertFalse(error);self.assertTrue(warn)
    def test_visual_with_images_passes(self):
        body=BODY.replace("pr-type: feature","pr-type: visual").replace("evidence: none","evidence: visual").replace("evidence-status: none","evidence-status: visual=passed")
        body+="\n## Visual比較\nBefore ![before](https://github.com/org/repo/assets/a.png)\nAfter ![after](https://github.com/org/repo/assets/b.png)\n"
        self.assertEqual(check(body,"表示変更：画面の配置を改善"),([],[]))
    def test_bad_status_fails(self):
        body=BODY.replace("evidence: none","evidence: visual").replace("evidence-status: none","evidence-status: visual=success")
        self.assertTrue(check(body)[0])
    def test_unobserved_device_success_fails(self):
        body=BODY.replace("evidence: none","evidence: platform").replace("evidence-status: none","evidence-status: platform=not_observed")
        body+="\n## Platform検証\nPlatform Switch。検証状態は未観測。実機 PASS。\n"
        self.assertTrue(check(body)[0])
    def test_unfilled_templates_must_fail(self):
        for kind, title in (
            ("feature", "機能追加：新規操作を登録"),
            ("fix", "不具合修正：初回適用時の問題を修正"),
            ("performance", "性能改善：Draw Callを削減"),
            ("visual", "表示変更：Prefab画面を変更"),
            ("qa", "テスト整備：回帰テストを追加"),
            ("infrastructure", "基盤変更：PR品質検証を追加"),
            ("maintenance", "保守：古い規約を更新"),
        ):
            path = Path(__file__).resolve().parents[2] / ".github" / "PULL_REQUEST_TEMPLATE" / (kind + ".md")
            errors, _ = check(path.read_text(encoding="utf-8"), title)
            self.assertTrue(errors, kind)

    def test_required_canonical_gate_includes_pr_validator(self):
        path=Path(__file__).resolve().parents[2]/".github"/"workflows"/"validate-agent-contracts.yml"
        content=path.read_text(encoding="utf-8")
        self.assertIn('Enforce Japanese PR title and required sections',content)
        self.assertIn('python tools/pr_quality/validate_pr.py --event "$GITHUB_EVENT_PATH"',content)
        self.assertIn('edited, ready_for_review',content)

    def test_event_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"event.json"
            path.write_text(json.dumps({"pull_request":{"title":"機能追加：明示的なCLI操作を追加","body":BODY}}),encoding="utf-8")
            exe=Path(__file__).with_name("validate_pr.py")
            p=subprocess.run([sys.executable,str(exe),"--event",str(path),"--json"],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertTrue(json.loads(p.stdout)["ok"])
if __name__=="__main__":unittest.main()
