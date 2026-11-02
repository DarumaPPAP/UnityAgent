# Python：責務ごとの比較例

共通原則は [Skill本体](../SKILL.md) を参照する。ここでは判定・適用・応答の配分と、Python固有の資源管理を示す。

## 教材の契約と範囲

以下は標準ライブラリだけで実行できる独立教材。関数はUnityAgentの実APIではなく、製品へ追加するための雛形でもない。

- 判定：Binding不一致は `binding_invalid`、一致してApproval無効なら `approval_invalid`、両方有効なら `accepted`。
- 適用：実判定を呼び、拒否時はDispatchせず、対象ファイルを維持し、拒否理由を1件記録する。受理時はDispatchする。
- 応答：処理中状態を開始し、拒否理由を受けてメッセージを表示した後に解除する。

Binding／Approvalは教材ではboolで表現する。署名の真正性・Project Identity照合、監査の永続保存、実OS Lock、実E2Eは検証しない。

## 悪い例

### 別の条件で先に拒否される

```python
def test_invalid_approval(self):
    self.assertNotEqual(verify(binding_matches=False, approval_valid=False), "accepted")
```

Binding拒否で通るため、Approval判定の誤りを検出できない。

### 適用境界の実判定をStubへ置き換える

次は説明用の断片。`module` は実 `verify` を呼び出す教材モジュール、`patch` は `unittest.mock.patch` を指す。

```python
with patch.object(module, "verify", return_value="approval_invalid"):
    result = apply(binding_matches=True, approval_valid=False, dispatch=dispatch, audit=audit)
```

これは拒否応答を受けた処理の確認には使えるが、実Verifierと適用処理の接続を確認できない。適用の戻り値だけをAssertする場合は、変更後に拒否する誤実装も通る。

### Fixtureに条件と期待値を隠す

```python
context = make_context(mode="reject", use_real=True, dirty=False)
result = context.run()
self.assertEqual(result, context.expected)
```

Binding、拒否条件、保護対象、期待値の根拠を追いにくい。応答テストで `stub.return_value` 自体をAssertするのも、呼び出し側の振る舞いを確認していない。

## 良い例：実行できる教材

判定の入力表は小さな判定テストへ置く。適用では拒否と受理の接続を確認し、応答ではStubを使う。Fixtureを分類ごとのFrameworkにせず、必要な一時領域と可変記録だけを準備する。

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock


def verify(binding_matches, approval_valid):
    if not binding_matches:
        # 異なる対象への要求を適用させない。
        return "binding_invalid"
    if not approval_valid:
        # 承認されていない要求を実行させない。
        return "approval_invalid"
    return "accepted"


def apply(binding_matches, approval_valid, dispatch, audit):
    result = verify(binding_matches, approval_valid)
    if result != "accepted":
        audit.append(result)
        # 拒否を記録した後、変更実行へ進ませない。
        return result
    dispatch()
    return result


def submit(evaluate, view):
    view["busy"] = True
    result = evaluate()
    view["message"] = "承認が無効です。" if result == "approval_invalid" else result
    view["busy"] = False


class DecisionTests(TestCase):
    def test_outcomes(self):
        cases = [(False, True, "binding_invalid"), (True, False, "approval_invalid"), (True, True, "accepted"), (False, False, "binding_invalid")]
        for binding, approval, expected in cases:
            with self.subTest(binding=binding, approval=approval):
                self.assertEqual(verify(binding, approval), expected)


class ApplyTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="apply-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audit = []

    def test_invalid_approval(self):
        target = self.root / "target.txt"
        target.write_bytes(b"original")
        dispatch = Mock(side_effect=lambda: target.write_bytes(b"updated"))

        result = apply(binding_matches=True, approval_valid=False, dispatch=dispatch, audit=self.audit)

        self.assertEqual(result, "approval_invalid")
        dispatch.assert_not_called()
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(self.audit, ["approval_invalid"])

    def test_valid_approval(self):
        target = self.root / "target.txt"
        target.write_bytes(b"original")
        dispatch = Mock(side_effect=lambda: target.write_bytes(b"updated"))

        result = apply(binding_matches=True, approval_valid=True, dispatch=dispatch, audit=self.audit)

        self.assertEqual(result, "accepted")
        dispatch.assert_called_once_with()
        self.assertEqual(target.read_bytes(), b"updated")
        self.assertEqual(self.audit, [])


class ResponseTests(TestCase):
    def test_rejection(self):
        view = {"message": "", "busy": False}

        def evaluate():
            self.assertTrue(view["busy"])
            return "approval_invalid"

        submit(evaluate, view)

        self.assertEqual(view["message"], "承認が無効です。")
        self.assertFalse(view["busy"])


if __name__ == "__main__":
    main()
```

`DecisionTests` はI/Oを使わない。最後の入力は、両方無効ならBinding拒否を優先する教材の契約を確認する。`ApplyTests` は実 `verify` を通し、変更実行の境界だけをSpyとして扱う。`ResponseTests` は応答をStubし、画面相当の状態を確認する。実画面への描画は含まない。

`ResponseTests` の `evaluate` は拒否応答を返すStubで、評価中に処理中状態であることも観測する。開始・解除の両方を削除した実装を、終了時のFalseだけで通してしまわない。呼出し回数は契約にないため確認しない。

## Fixtureと命名の読み方

- 一時領域の作成・解放と監査Listの初期化は共通準備。Binding・Approval・ファイルの初期内容・期待結果はケース内に残す。
- 数行のファイル準備は直接書く。現状の重複を除くためだけのBuilderや、多数のフラグを持つContextは作らない。
- `test_invalid_approval` の文脈は `ApplyTests` が示す。全Assertionを名前へ列挙しない。同じクラス内で異なる条件が増えた場合に識別語を追加する。
- `subTest` は同じ判断規則の入力表を識別する用途。可変Fixtureを再利用する場合は各反復を独立させる。
- `addCleanup` は確保直後に登録する。`setUp` 失敗時には `tearDown` が呼ばれない。変更する環境変数・時刻等も必要な範囲だけ復元する。

このファイルの3テストクラスは責務を比較する教材上の区切りであり、実Projectで同じ数のクラス・ファイルを要求しない。

## 観測の限界

無変更の観測は `target.txt` の内容と存在だけ。新規ファイルの追加、ACL、時刻、別の保存先、非同期の後続処理は証明しない。それらが契約に含まれる場合に対応する観測を追加する。監査Listは永続Evidenceではなく、保存を担当する境界は実保存・読み戻しで別途確認する。
