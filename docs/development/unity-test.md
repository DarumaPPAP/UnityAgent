# UnityAgent 開発・検証環境 仕様書

> **2026-10-27 テスト基盤リセット**：現役の `tests/` は `tests/UnityAgentTest/` のみ。以下に登場する旧 `tests/unity/` Fixture と旧Regressionは削除済みの移行前記述であり、現在の検証手順として実行しない。必要な旧内容はGit Revision `77483d6ecc656b8842954cd509de5d9ce7224c2f` を参照する。製品のRegressionは `NOT_CONFIGURED`、Releaseは禁止。UPMに内包した別個の検証ソースの存在をUnity実行Evidenceと取り違えない。

**文書名:** `unity-test.md`
**対象:** `DarumaPPAP/UnityAgent`
**状態:** Design確定・実装待ち
**方針:** KISS / 既存Runtime再利用 / 実測重視

## 1. 目的

UnityAgentのRepositoryをUnity Projectとして利用できるようにし、単一のテスト用Unity Projectを通して本番UnityAgentの動作を検証できる環境を整備する。

あわせて、公開CLIを`uagent`に統一し、毎回Project Pathを指定しなくても操作できるようにする。

今回のUnity動作確認は、ユーザー本人がUnity Editorで行う。

## 2. 確定Decision

| ID | Decision |
|---|---|
| D01 | 公開CLIは`uagent`で統一する |
| D02 | 通常はCWDからUnity Projectを自動検出する |
| D03 | 別Projectの指定には`--project-p`を使用する |
| D04 | 既存`--project-path`は互換エイリアスとして維持する |
| D05 | RepositoryルートをUnity開発Projectとして利用する |
| D06 | 標準Unity Test Projectは`tests/UnityAgentTest/`の1つ |
| D07 | 本番CLI / Control Plane / UPMを再利用する |
| D08 | Project Runner Pinと独自Dispatcherを新設しない |
| D09 | Development / ReleaseのRevision整合契約を維持する |
| D10 | Unity Editorの実行確認は当面ユーザーが行う |
| D11 | 未観測のUnity Gateは`BLOCKED_NOT_RUN`とする |

## 3. Repository構成

```text
UnityAgent/
├── .agents/
│   └── skills/
├── .github/
│
├── Assets/                        # 開発用Project
├── Packages/
│   ├── manifest.json
│   └── com.darumappap.unity-agent/
│       ├── package.json
│       └── Editor/
├── ProjectSettings/
│
├── src/
│   └── unityagent/                # 本番Python / Control Plane
├── subagent/
│
├── ci/
├── docs/
├── scripts/
├── tests/
│   ├── UnityAgentTest/           # 標準UnityテストProject
│   │   ├── Assets/
│   │   │   └── Tests/
│   │   │       ├── EditMode/
│   │   │       └── PlayMode/
│   │   ├── Packages/
│   │   │   └── manifest.json
│   │   ├── ProjectSettings/
│   │   └── README.md
│   ├── runtime/
│   └── unity/                     # 既存Fixture：移行まで維持
└── tools/
```

既存の製品コード、SubAgent、UPM Package名は変更しない。

`.uagent/`は今回新設しない。将来、既存機能では満たせないProject固有設定が必要になった場合だけ導入を再検討する。

## 4. CLIの公開仕様

### 4.1 正式コマンド名

`uagent`

現行の`unityagent.cli:main`をそのままEntrypointとして利用する。

`unity-agent`は互換性維持のため当面残す。ただし新規ユーザー向けDocumentationでは`uagent`を標準とする。

### 4.2 Project自動検出

Project Path解決の優先順位：

1. `--project-p`による明示指定
2. `--project-path`による旧形式の明示指定
3. CWDから親ディレクトリ方向へのProject探索
4. 見つからなければエラーで停止

`--project-p`と`--project-path`を同時に与えた場合は曖昧な入力として拒否する。

Project判定条件：

- `Assets/`が存在する
- `Packages/manifest.json`が存在する
- `ProjectSettings/ProjectVersion.txt`が存在する

探索では最も近いProject Rootを採用し、それより上位にある別Projectへ不用意に切り替えない。

解決したPathは正規化し、既存のProject IdentityおよびEditor Bindingと照合する。

現在接続されているUnity Editorだけを理由に、別Projectへ自動切替しない。

**CWD・明示指定のどちらでも、Mutation ScopeとApprovalの検証は省略しない。**

### 4.3 標準的な操作

```powershell
cd D:\UnityAgent\tests\UnityAgentTest

uagent doctor
uagent setup plan
uagent setup apply
uagent e2e plan
```

`setup apply`には既存Contractに必要な承認情報を指定する。

別Projectの場合：

```powershell
uagent doctor --project-p D:\Projects\MyGame
uagent e2e plan --project-p D:\Projects\MyGame
```

相対パスも利用可能とする。

```powershell
uagent doctor --project-p ..\MyGame
```

### 4.4 CLI構文

| 用途 | 正式構文 |
|---|---|
| Help | `uagent --help` |
| 診断 | `uagent doctor` |
| Setup計画 | `uagent setup plan` |
| Setup適用 | `uagent setup apply` |
| Task実行 | `uagent run --request <file>` |
| E2E計画 | `uagent e2e plan` |
| E2E承認 | `uagent e2e approve` |
| E2E保存承認 | `uagent e2e approve-save` |
| E2E適用 | `uagent e2e apply` |

既存の`setup --operation plan`等は互換性を維持する。

`run --request`のようにRequest側がProject Bindingを所有するコマンドは、既存Contractを優先する。CWDから勝手にBindingを上書きしない。

## 5. Plan / Applyの安全性

Planは対象Projectの正規化済みPathとProject Identityに結び付ける。

Apply時には以下を確認する。

- 対象ProjectがPlanと一致する
- Approvalが対象Projectに有効
- Mutation Scopeが変わっていない
- Revision / 定義Fingerprintが一致
- 実行中Editorが正しいProjectを開いている

Plan生成後にCWDを変更しても、別ProjectへApplyできてはならない。

既存のPlan / Approval / Evidence契約を再利用する。CLI改修を理由に新しい承認管理基盤は追加しない。

## 6. ファイル命名規則

原則は「短い・読みやすい・責務が明確」。

新しい文書とテストファイルの標準名：

| ファイル | 用途 |
|---|---|
| `unity-test.md` | 仕様書 |
| `unity-setup.md` | Codex Cloud指示書 |
| `README.md` | 手動確認手順 |
| `EditTests.cs` | EditMode Test |
| `PlayTests.cs` | PlayMode Test |
| `EditTests.asmdef` | EditMode Test Assembly |
| `PlayTests.asmdef` | PlayMode Test Assembly |

既存の公開Class、Schema、Package名、Unity標準ファイル名は短縮目的で変更しない。

ディレクトリ名で意味が明確な場合、ファイル名に同じ単語を重複させない。

例：

`Assets/Tests/EditMode/EditTests.cs`

一方、Unityの`.asmdef`内部Assembly名は衝突を避けるため、必要な名前空間を保持する。

## 7. Unity Test Project

### 7.1 環境

- Unity `6000.3.12f1`
- URP `17.3.0`
- Unity Test Framework `1.6.0`
- 本番`com.darumappap.unity-agent`

テストProjectのManifest：

```json
{
  "dependencies": {
    "com.darumappap.unity-agent": "file:../../../Packages/com.darumappap.unity-agent",
    "com.unity.render-pipelines.universal": "17.3.0",
    "com.unity.test-framework": "1.6.0"
  }
}
```

これは既存Repository構造を前提とした目標内容。実際のUnity Package Managerで依存解決を確認する。

ルートProjectは既存UPMをEmbedded Packageとして使用する。Manifestで同じPackageを不必要に二重指定しない。

### 7.2 テスト構成

EditMode：

- Packageの読み込み
- Editor拡張
- AssetDatabase操作
- Editor側Contract

PlayMode：

- MonoBehaviour Lifecycle
- Scene / GameObject
- Runtime動作
- PlayMode中の観測

E2E：

- 既存の本番`uagent e2e`
- Control Plane
- Policy / Approval
- Unity Editor Bridge
- Evidence

E2E用の新規Unity Projectは作らない。

EditModeとPlayModeは別Assemblyで分離するが、同じ`UnityAgentTest`内で実行する。

## 8. 手動テスト運用

Unity Editorテストは当面ユーザーが実行する。

基本手順：

1. Unity Hubから`tests/UnityAgentTest`を開く。
2. Unity `6000.3.12f1`を使用する。
3. Package Managerの読み込みが終わるまで待つ。
4. ConsoleのCompile Errorを確認する。
5. `Window > General > Test Runner`を開く。
6. EditModeの`Run All`を実行する。
7. PlayModeの`Run All`を実行する。
8. ConsoleとTest Runnerの結果を確認する。

Full E2Eは必要時に別途実施する。実行前には保存済みScene、対象Asset不存在、実行中Editor、承認、Project外側のState Rootなど既存のFull E2E前提条件を満たす。

結果はCompile、EditMode、PlayMode、Full E2Eごとに区別する。

ユーザーが確認していない項目をPASSにしない。

## 9. Revision整合

新しいRunner Pinを作らず、既存契約を利用する。

Development：

- レビュー済みGit Commit SHAを固定
- UPM / Host CLIの対応を検証
- 未レビュー変更を検証済みRevisionに混同しない

Release：

- 検証済みCommitからSemVer / Tagを生成
- Package / CLI / その他成果物の整合を確認
- 既存P9 Release Gateを維持

Git SHAをログに記録しただけでは、実行中のUPMとHostが同一Revisionだった証明にはならない。実装上確認できない整合性は未検証と扱う。

## 10. 旧Fixtureの扱い

既存`tests/unity/projects/`のFixtureは初回PRで削除しない。

特に以下の契約を維持する。

- `tests/unity/matrix.yaml`
- P9 Source Manifest
- UPM Verification Mirror
- Package / Fixtureパス
- Release Evidence Gate

今後の標準テスト追加先は`tests/UnityAgentTest/`とする。

既存のUnity Version別・Pipeline別Fixtureは、新しい標準Projectで同等の検証を実測できるまで維持する。別Projectを増やさない原則は、必要な互換性検証を破壊する根拠にはならない。

## 11. 完了条件

### Codex Cloud側

- `uagent`が正式公開CLIになる
- CWDからProjectを検出できる
- `--project-p`が利用できる
- 旧`--project-path`が動作する
- Plan / ApplyのProject Bindingを維持する
- RepositoryルートがUnity Project構成を持つ
- `UnityAgentTest`の準備が完了する
- 既存Static / Host / Packaging検証がPASS
- 手動テスト手順がREADMEに記載される
- PRが作成される

### ユーザー側

- Unity Package Import
- Compile
- EditMode
- PlayMode
- 必要なFull E2E

Unity検証が未実施の場合、PRは`READY_FOR_MANUAL_TEST`として引き渡す。

**Unity Editor未実行のままFull E2E完了とはしない。**
