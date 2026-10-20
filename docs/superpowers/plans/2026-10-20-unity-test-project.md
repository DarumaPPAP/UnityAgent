# Unity開発・検証環境 実装計画

**Goal:** 公開CLIをuagentに揃え、ProjectをCWDから検出し、標準Unity Projectで手動検証できる状態にする。
**Architecture:** CLI入口で既存Project Identityへ正規化し、Control Planeの承認・Evidence契約へ渡す。UPMと既存Fixtureは保持する。
**Tech Stack:** Python argparse / unittest、Unity 6000.3.12f1、URP 17.3.0、Test Framework 1.6.0。
**Spec:** [unity-test.md](../../development/unity-test.md)、[unity-setup.md](../../development/unity-setup.md)。ユーザー確定仕様・実装指示に従い本セッションで実装する。

## 制約とレビュー重点

- run --requestのBinding、既存Approval、Revision/Fingerprint、P9 Mirrorを維持。
- 明示した無効Pathでは親ProjectへFallbackしない。最寄りProject、相対Path、Symlink、空文字を検証する。
- 両Projectフラグとsetup操作指定の競合を拒否する。
- Planを参照するrock / rock-import / hot-reloadはCLI対象との照合後に既存処理へ渡す。
- Unity未実行GateはBLOCKED_NOT_RUN。SceneやLockを捏造しない。

## Task 1: CLI互換性・Project検出

- [x] tests/runtime/test_project_cli.pyで明示指定、CWD直下・子階層・ネスト、Project不在、不正Path、競合、setup互換、run Bindingをテストする。
- [x] unittestで失敗を確認する。
- [x] cli.pyで同じdestの排他Projectフラグとsetup位置引数を追加。project_identity.pyにresolve_project_root(project_root=None, *, cwd=None)を追加し既存正規化を再利用する。
- [x] Plan参照コマンドの既存Persistence読取で対象Projectを照合する。別ProjectのApprove / Apply / Rollbackが副作用前に拒否されるテストを追加する。
- [x] pyproject.tomlへuagentを追加。旧エイリアスとInstaller経路は保持する。
- [x] CLI回帰と既存Setup / Full E2E / Hot Reload / RockのHostテストを実行する。

## Task 2: Unity Project・手順

- [x] Assets/、Packages/manifest.json、ProjectSettings/ProjectVersion.txtとrepository-layout.jsonを整備する。
- [x] tests/UnityAgentTestへ指定Manifest、EditTests / PlayTestsとasmdef / metaを追加する。
- [x] EditModeで本番Package / AssemblyとAssetDatabase、PlayModeでMonoBehaviour / Sceneを確認する。
- [x] READMEにUnity Hub、Import、Console、Test Runner、Scene保存、Full E2E独立承認、Revision整合の限界を記す。
- [x] READMEと公開CLI手順をuagentへ更新する。破壊的一括置換はしない。
- [x] Layout / Manifest / Packaging / P9 Mirrorの既存検証を実行する。

## Task 3: 検証・引き渡し

- [x] python tools/validate_all.pyと既存CI相当のFixture検証を実行する。
- [x] CLIをインストールし両EntrypointのHelpとCWD / 明示指定を検証する。
- [ ] 差分のレビュー、必要な修復、再検証後にCommit / Push / PRを作成する。
- [ ] CI結果を確認し、Host結果とUnity未実行Gateを分けてREADY_FOR_MANUAL_TESTとして報告する。

## 実装検証記録

- `PYTHONDONTWRITEBYTECODE=1 python tools/validate_all.py`: PASS（13 Suite、757 Tests、既存Skip 1件）。
- 独立venvへのwheelインストールと両CLI Help、CWD / 新旧Projectフラグ: PASS。
- `tests/unity/verify/validate_unity_fixtures.py`: 静的PASS、Host Runner 55 Tests PASS。
- 標準ProjectのManifest相対参照、Version、Assetのmeta / GUID: 静的PASS。
- 独立コードレビュー: 重要指摘なし。Unity Compile / Lifecycleは未観測。
- Cloud既定のユーザー領域が書き込み不可だったため、既存OS共有ロック領域への権限を付与してHost検証を実施。製品のロック契約は変更していない。
- 検証中の再インストールは生成Resourcesを置き換えるため、最終検証ではビルドとテストを直列実行。P9 Mirrorへの生成キャッシュ混入を避けるためbytecode生成を無効化。
- Unity Package Import / Compile / EditMode / PlayMode / Full E2Eはすべて `BLOCKED_NOT_RUN`。
