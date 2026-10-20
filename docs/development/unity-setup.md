# Codex Cloud実装指示 — UnityAgent環境整備

**文書名:** `unity-setup.md`
**Repository:** https://github.com/DarumaPPAP/UnityAgent
**Branch:** `feature/unity-test-project`

## Goal

UnityAgentの公開CLIを`uagent`へ統一し、CWDからProjectを自動検出できるようにする。

同時に、RepositoryルートをUnity開発Projectとして整備し、単一の`tests/UnityAgentTest/`で手動Unity検証できる環境を準備する。

**Unity Editorによる動作確認はユーザーが実施する。Codex Cloudは実装、Host検証、PR作成まで担当する。**

## 1. 守るべき契約

着手前に最新`main`を取得し、次を確認する。

- `AGENTS.md`
- `repository-layout.json`
- `.github/branch-policy.json`
- `src/unityagent/policy/`
- `src/unityagent/contracts/repository-authority-map.yaml`
- `src/unityagent/cli.py`
- `src/unityagent/runtime/tooling/environment/`
- `pyproject.toml`
- `setup.py`
- `Packages/com.darumappap.unity-agent/`
- `tests/unity/`
- `tests/packaging/test_editor_bundled_verification.py`
- `docs/architecture/full-e2e-capability.md`
- `docs/development/p9-release-qualification.md`

Repositoryの既存実装と正本契約が提案と衝突する場合は、FactとDecisionを区別して判断する。

既存のPolicy・Approval・Runtime・Evidenceを迂回する実装は禁止。

## 2. CLIの`uagent`統一

### 2.1 Console Script

`pyproject.toml`の`[project.scripts]`に正式な`uagent`を登録する。

同一Entrypointを使用する。

```toml
[project.scripts]
uagent = "unityagent.cli:main"
unity-agent = "unityagent.cli:main"
```

`unity-agent`は既存連携用の互換エイリアス。

既存のPython Package名、Module名、Control Planeは変更しない。

新しい公開DocumentationとUsageでは`uagent`を使用する。

旧コマンド名がInstaller、Bootstrap、CI、Plugin等に使われている箇所を調査し、破壊的な一括置換を避ける。

### 2.2 Project Path Resolver

既存のProject Identity / Environment Discoveryを調査し、再利用する。

目標動作：

```text
uagent doctor
    ↓
--project-p がある？
    ├─ Yes → 指定Projectを検証
    └─ No
         ↓
    --project-path がある？
         ├─ Yes → 旧形式の指定Projectを検証
         └─ No → CWDからProject Rootを探索
                       ↓
                  正規化・検証
                       ↓
                  Control Plane
```

両フラグ同時指定はエラー。

CWD探索は親方向のみ。子フォルダの全走査はしない。

Unity Project判定：

- `Assets/`
- `Packages/manifest.json`
- `ProjectSettings/ProjectVersion.txt`

最初に見つかった最も近いProjectを選ぶ。

Projectが見つからなければエラー終了し、明示指定方法を案内する。

ユーザーの指定なしに接続中Editorの別Projectへ切り替えない。

既存のProject Identity正規化と一致させる。

### 2.3 対象コマンド

Project Pathが必要な公開コマンドの必須引数を見直す。

対象：

- `doctor`
- `setup`
- `e2e`
- `rock`
- `rock-import`
- `hot-reload`

既存の`run --request`など、RequestがProject Bindingを所有する経路は既存仕様を維持する。

目標構文：

```powershell
uagent doctor
uagent setup plan
uagent setup apply
uagent e2e plan
uagent e2e approve
uagent e2e approve-save
uagent e2e apply
```

各操作で必要なPlan ID、Approval Ref等の指定は従来どおり維持する。

`setup`は位置引数形式を追加し、従来の`--operation`形式も維持する。

内部処理やResult Schemaを変更せず、CLI入口だけを最小変更する。

### 2.4 Safety

- Project Rootを正規化する。
- 不正Projectや不存在Pathを拒否する。
- PlanとApplyで対象Projectの一致を検証する。
- Editor Bindingを再検証する。
- 誤ったProjectにMutationしない。
- Approvalを省略しない。
- 意図しないProject切替をしない。
- 別のProject設定DBやPinを作らない。

Project解決方法の単体テストは、既存のCLI / Hostテストに必要最小限追加する。

最低限、明示指定、CWD直下、CWD子階層、ネストしたUnity Project、Project不在、両フラグ競合、Plan / Apply不一致を検証する。

## 3. RepositoryルートのUnity Project化

以下を最小限整備する。

```text
Assets/
Packages/
ProjectSettings/
```

Unity Versionは`6000.3.12f1`とする。

既存の`Packages/com.darumappap.unity-agent/`は移動しない。

UPMをコピーせず、Embedded Packageとして利用する。

`Packages/manifest.json`に同じEmbedded Packageの不要な自己参照を追加しない。

`repository-layout.json`と`.gitignore`を必要最小限更新する。

Unity Editorを起動できない場合、`.unity` SceneやPackage Lockが実Unityで生成・検証されたと偽装しない。

## 4. UnityAgentTest構築

作成先：

```text
tests/UnityAgentTest/
├── Assets/
│   └── Tests/
│       ├── EditMode/
│       │   ├── EditTests.asmdef
│       │   └── EditTests.cs
│       └── PlayMode/
│           ├── PlayTests.asmdef
│           └── PlayTests.cs
├── Packages/
│   └── manifest.json
├── ProjectSettings/
│   └── ProjectVersion.txt
└── README.md
```

必要なUnity `.meta`ファイルとasmdef参照を正しく用意する。

C#テストとAssembly DefinitionはUnity Test Frameworkの契約に従う。

テストは少数の意味あるSmoke Testとし、常に成功するだけの無意味なAssertは作らない。

必要な実Unity Sceneは、ユーザーによるUnity Editor確認時に生成できるようREADMEへ手順を記載する。

初期環境：

- Unity `6000.3.12f1`
- URP `17.3.0`
- Unity Test Framework `1.6.0`
- 本番UPMを相対パス参照

`UnityAgentTest/Packages/manifest.json`では以下を利用する。

```json
"com.darumappap.unity-agent": "file:../../../Packages/com.darumappap.unity-agent"
```

`packages-lock.json`は実際のPackage Managerによる解決を確認できた場合のみ採用する。

## 5. 手動Unityテスト用README

`tests/UnityAgentTest/README.md`は短く明確に書く。

記載する内容：

1. Unity HubでProjectを開く手順
2. Unity Version
3. Package Import確認
4. Console確認
5. Test Runnerの開き方
6. EditModeテスト実行
7. PlayModeテスト実行
8. エラー発生時に共有すべき情報
9. 必要に応じたFull E2E実行の前提条件

Full E2Eは本番`uagent e2e`を使用する。

固定Full E2Eには保存済みScene、Editor接続、対象Asset不存在、Project外State Root、別々のApprovalが必要であることを明記する。

自動承認機構を新設しない。

## 6. Revision整合

既存のDevelopment / Release分離を維持する。

- Development：レビュー済みCommit SHA固定
- Release：検証済みRevisionからSemVer / Tag
- UPMとCLIの実行Revision整合
- Evidenceと実行ソースの対応

新しい`.uagent/project-runner-pin.json`は作成しない。

既存機構でRevisionの証明が不十分な場合は、確認できたGapを報告する。既存Authorityと重複する新しい管理システムは導入しない。

## 7. 既存テストとCIの維持

初回PRでは次を削除しない。

- `tests/unity/projects/`
- `tests/unity/matrix.yaml`
- P9 Fixture
- Artist Fixture
- Pipeline Fixture
- UPM Verification Mirror
- Release Gate

特に`tests/packaging/test_editor_bundled_verification.py`のManifest整合を維持する。

新しい`UnityAgentTest`を標準テストProjectとし、旧Fixtureの移行・削除は今回行わない。

新規の自動Unity E2E CIは作成しない。

## 8. Cloud側の検証

実行可能な検証をすべて行う。

例：

```powershell
python tools/validate_all.py
```

加えて、既存検証手順を利用して以下を確認する。

- CLIインストールと`uagent --help`
- CWD解決
- `--project-p`
- 旧`--project-path`
- `setup`構文互換性
- Host回帰テスト
- Repository Layout
- Package Manifest参照
- Packaging / Authority
- 既存P9 Mirror整合

新しい専用テストFrameworkは作らない。

CloudにUnity Editorがない場合は、実Unity検証をPASS扱いしない。

## 9. PR作成

`feature/unity-test-project`を使用する。ただし同名Branchが存在する場合は、既存作業との衝突を確認して適切な別名を付ける。

PR本文には以下を記載する。

- 目的と変更範囲
- 変更したCLI仕様
- Project Path自動検出
- Unity Project構成
- 本番UPM参照
- 実行したHost / Static検証
- 未実施のUnity検証
- ユーザー用手動テスト手順
- 未解決リスク

必要なCIを確認し、失敗があれば原因を調査・修正する。

Merge、Release、Tag、既存Fixtureの破壊的削除は禁止。

## 10. 最終報告

次のようにGateを分離する。

| Gate | 結果 |
|---|---|
| CLI / Project解決 | 実行結果 |
| Host / Packaging | 実行結果 |
| Repository Layout | 実行結果 |
| Unity Package Import | BLOCKED_NOT_RUN |
| Unity Compile | BLOCKED_NOT_RUN |
| Unity EditMode | BLOCKED_NOT_RUN |
| Unity PlayMode | BLOCKED_NOT_RUN |
| Unity Full E2E | BLOCKED_NOT_RUN |

実際に実行したGateのみ結果を更新する。

Cloudでの実装・Host検証・PR作成が完了したら`READY_FOR_MANUAL_TEST`と報告し、ユーザーによるUnity Editor確認へ引き渡す。

**この状態はUnity実機検証の成功を意味しない。**
