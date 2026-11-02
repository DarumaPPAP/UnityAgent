# 判断根拠と参照先

このSkillの中心契約はユーザーが選択した「振る舞い・不変条件を単位にし、拒否結果と禁止された副作用の不在を一組で守る」方針。外部資料はその適用を支える根拠であり、対象Projectの正本・ユーザー指示を上書きしない。

## 公式資料

- [Unity 6.3：Testing your code](https://docs.unity.com/ja-jp/engine/6000.3/manual/programming-environment/test-framework-introduction)／[Unity 6.6](https://docs.unity.com/ja-jp/engine/6000.6/manual/programming-environment/test-framework-introduction)：Version別の入口。入口の説明が似ていてもPackage/APIの全互換性は仮定しない。
- [Unity：Edit mode and Play mode tests](https://docs.unity3d.com/6000.3/Documentation/Manual/test-framework/edit-mode-vs-play-mode-tests.html)：実行環境とTest／UnityTestの選択。
- [Unity：Asynchronous tests](https://docs.unity3d.com/6000.3/Documentation/Manual/test-framework/reference-async-tests.html)：async TaskとAssert.ThrowsAsyncの注意。
- [Python：unittest](https://docs.python.org/3/library/unittest.html)：subTest、addCleanup、setUp／tearDown。実際のPython Versionに対応する記述を確認する。
- [Google：Tests Too DRY? Make Them DAMP!](https://testing.googleblog.com/2019/12/testing-on-toilet-tests-too-dry-make.html)：意図を追いやすくする共通化は許容し、可読性を優先する。
- [Google：Prefer Narrow Assertions](https://testing.googleblog.com/2024/04/prefer-narrow-assertions-in-unit-tests.html)：関係しない属性の固定を避ける。保護契約に必要なAssertionまで削らない。
- [Google：Code Coverage Best Practices](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)：カバレッジは未実行領域を探す指標であり、一律の品質保証値ではない。

## 適用条件を伴う事例

- [実プレイ由来SnapshotによるE2E再構築](https://zenn.dev/unsoluble_sugar/articles/57d4ca55ef1ef1)：代表的E2Eの前提を忠実にする考え方を参考にする。拒否・破損Fixtureまで正常経路由来に限定しない。
- [自動テストの肥大化とどう向き合うか](https://zenn.dev/frontendflat/articles/automated-test-size-tradeoff)：独自検出価値と運用コストを評価する。掲載された実行時間・配分を別Projectへ転用しない。

## UnityAgent内で作業する場合

適用中のAGENTS.mdと、そこから解決される現行Policy・Contract・コードを確認する。`test-lifecycle` はテスト採用・廃止・一時Probeの運用を扱う。このSkillはそれらの正本やRuntimeのApproval Authorityを代替しない。過去のテスト件数、未実装シナリオ、固定のProject Versionを普遍的な前提として保持しない。
