# Unity C#：責務ごとの比較例

共通原則は [Skill本体](../SKILL.md) を参照する。ここではUnity側で、実Verifier・応答Stub・Object所有権をどう使い分けるか示す。

## 例の前提

以下は既存Projectの構造へ対応付けるための抜粋。API名・型名は説明用であり、UnityAgentの実APIではない。対象実装やFixtureの組立ては省略しているため、単独ではコンパイル・実行できない。例のために製品APIを追加しない。

契約は、Binding一致・Approval無効なら `approval_invalid` で拒否し、Dispatchせず、保護対象のObjectを維持し、拒否理由を1件記録すること。正常系は受理・実行を確認する。

適用テストの `_entry` は実Verifierを使用する。`_binding` は有効、`_invalidApproval` は狙った条件だけ無効。`_dispatchCount` と `_auditReasons` はケースごとに初期化し、対象へ作用する変更Backendの境界で呼出しを記録する。暗黙のFixture既定値でこれらの意味を隠さない。

## Assertion：判定と適用

悪い判定例は、Binding不一致による先行拒否でも通る。

```csharp
[Test]
public void RejectsInvalidApproval()
{
    var request = CreateRequest(binding: _otherBinding, approval: _invalidApproval);
    Assert.That(_verifier.Evaluate(request).Accepted, Is.False);
}
```

良い判定例では、実Verifierへ狙った入力を渡す。変更処理のFixtureは不要。

```csharp
[Test]
public void RejectsInvalidApproval()
{
    var request = CreateRequest(binding: _binding, approval: _invalidApproval);

    var decision = _verifier.Evaluate(request);

    Assert.That(decision.Accepted, Is.False);
    Assert.That(decision.Reason, Is.EqualTo("approval_invalid"));
}
```

適用境界では、戻り値だけをAssertすると、変更後に拒否する実装も通る。次の良い例は、実判定と実行抑止の接続を確認する。

```csharp
[Test]
public void RejectsInvalidApproval()
{
    var target = CreateTarget("Original");
    var request = CreateRequest(binding: _binding, approval: _invalidApproval, target: target);

    var result = _entry.Apply(request);

    Assert.That(result.Accepted, Is.False);
    Assert.That(result.Reason, Is.EqualTo("approval_invalid"));
    Assert.That(_dispatchCount, Is.Zero);
    Assert.That(target != null, Is.True);
    Assert.That(target.name, Is.EqualTo("Original"));
    Assert.That(_auditReasons, Is.EqualTo(new[] { "approval_invalid" }));
}
```

判定例と適用例は別の責務を持つテスト群へ置く想定。同じクラスに同名メソッドを配置しない。適用では判定条件の全入力表を複製せず、別ケースで有効Approvalの受理・Dispatchも確認する。

## Mock：実判定と応答Stub

適用テストで `_verifier` をStubへ交換すると、拒否応答後の分岐は確認できても実Verifierとの接続は未検証になる。

呼び出し側の表示が対象ならStubを使える。悪い例は設定値を読み返すだけで、画面処理を呼んでいない。

```csharp
_verifier.Result = Decision.Reject("approval_invalid");
Assert.That(_verifier.Result.Reason, Is.EqualTo("approval_invalid"));
```

良い例は、実Presenterの処理を通して表示内容と状態を観測する。この例の `_verifier` は `Func<Decision>` を受け取る `Evaluate` プロパティを持つ応答Stubで、Presenterからの評価要求時にその関数を実行する想定。`_view` は表示状態を記録するテスト用実装。処理中状態の開始・解除はPresenterの責務とする。

```csharp
[Test]
public void ShowsRejection()
{
    _view.IsBusy = false;
    _verifier.Evaluate = () =>
    {
        Assert.That(_view.IsBusy, Is.True);
        return Decision.Reject("approval_invalid");
    };

    _presenter.Submit();

    Assert.That(_view.Message, Is.EqualTo("承認が無効です。"));
    Assert.That(_view.IsBusy, Is.False);
}
```

Verifierの呼出し回数が契約でなければAssertしない。このテストは実Verifierの判定、UIとの実配線、実画面への描画を保証しない。

評価中のTrueと終了時のFalseを観測し、開始・解除の両方を削除した実装も検出する。解除だけが呼び出し側の責務なら、処理中の初期状態を明示して解除を確認する。例のDelegate設定は既存のStub機構へ対応付け、同じプロパティを製品へ追加しない。

## Fixture：所有物だけを準備・解放する

悪い例は既存Assetをテスト所有とみなして削除する。

```csharp
[SetUp]
public void SetUp()
{
    _target = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Prefabs/Player.prefab");
}

[TearDown]
public void TearDown()
{
    AssetDatabase.DeleteAsset("Assets/Prefabs/Player.prefab");
}
```

良い例では、複数ケースで繰り返す生成・所有登録だけをHelperへまとめ、名前や条件はケースに残す。`Object` は `UnityEngine.Object` の別名を使う。必要なusingは対象ファイルに追加する。

```csharp
private readonly List<GameObject> _created = new List<GameObject>();

private GameObject CreateTarget(string name)
{
    var target = new GameObject(name);
    _created.Add(target);
    return target;
}

[TearDown]
public void TearDown()
{
    foreach (var target in _created)
    {
        if (target != null)
        {
            Object.DestroyImmediate(target);
        }
    }

    _created.Clear();
}
```

`CreateTargetAndRegisterForAutomaticCleanup` のように手順を列挙しない。単発ならHelperを作らず、生成物の参照保持と解放を直接記述できる。既存テストに同じ所有管理があれば再利用する。

このCleanupは `_created` だけを扱う。監査記録・呼出し数・その他の可変状態の初期化は別途必要。共有Sceneを保存・閉鎖する処理は追加しない。

## Unity固有の適用基準

| 判断 | 基準 |
| --- | --- |
| EditMode／PlayMode | GameObjectの有無ではなくEditor API・PlayerLoop・Lifecycleへの依存で選ぶ |
| Test／UnityTest | 同期処理は `[Test]`。Unity固有yieldやフレーム経過が必要な場合に `[UnityTest]` を使う |
| 非同期 | 対象Versionで対応する戻り値型を確認し、完了・Cancel・例外を観測する。メインスレッドを待機でブロックしない |
| 非同期例外 | Unity 6.3公式には `Assert.ThrowsAsync` によるEditor停止の注意がある。対象Versionを確認し、必要ならawaitで例外を検証する |
| ログ | 仕様上期待するログだけ `LogAssert.Expect` で確認する。Errorの削除・格下げや広域ignoreで成功させない |
| 解放 | 上のEditMode例はDestroyImmediate。PlayModeでDestroy完了まで必要なら、対象の寿命に合わせUnityTearDown等で待つ |
| Asset／状態 | 保存が対象ならテスト所有のAsset領域で実保存を観測する。変更したTime・Random・イベント購読等は復元する |

API仕様の確認先は [原典](sources.md) を参照する。

## 観測の限界

適用例が確認する保護対象はObjectの存在と名前だけ。Transform・Component・Scene全体・Assetファイルの無変更を保証しない。監査Listも永続保存ではない。これらが対象の契約に含まれる場合に観測を追加する。

抜粋の読解をCompileやEditModeのPASSに数えない。実行する場合は、既存の適切なテスト環境を優先し、対象Version・Assembly参照・Fixtureの所有範囲を確認する。共有環境へ影響する操作や、隔離しないと再現できない条件がある場合に、専用Projectや複製環境を使う。実際に実行した範囲を報告する。
