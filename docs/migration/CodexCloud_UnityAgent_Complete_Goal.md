<!-- DOCUMENT_TYPE: CODEX_CLOUD_EXECUTION_GOAL; CANONICAL_P1_P8; NOT_SPEC -->
# Codex Cloud 実行指示: UnityAgent + UnitySubAgentHub P1〜P8

**本ファイルは実行指示（Goal）であり、仕様書ではない。** 添付仕様書 `UnityAgent_Repository_Consolidation_Spec_v1.md` とは別のファイルである。P0は完了済みのため、**P1から再開**する。

## P0引継ぎ — このセクションを本文より優先

- UnityAgent PR [#173](https://github.com/DarumaPPAP/UnityAgent/pull/173) Squash Merge済み。SHA `007dbc66365a8c2ca26fa12cbc89d5b544d7339a`。
- UnitySubAgentHub PR [#93](https://github.com/DarumaPPAP/UnitySubAgentHub/pull/93) Squash Merge済み。SHA `83dcd6e7a2cba94e5bc0b4975579252da1d5e69a`。
- 両RepositoryのP0必須CheckはGreen、基準Test/Build PASSと報告済み。P0用PRは再作成しない。
- Unity Editor / License / 実機Gateは `BLOCKED_NOT_RUN`。未実行をPASSと記録しない。
- Codex workspace内 `/workspace/repository-consolidation-status.md` と両Repository `docs/migration/repository-consolidation-progress.md`, `docs/migration/repository-consolidation.md`, `docs/migration/consolidation/p0-inventory.json` を照合し、P0監査・再開記録を引き継ぐ。
- 本文にある「P0 Preflight」は差分・権限の再確認のみ意味する。P0を重複実装しない。

## P1〜P8 実行指示（追加承認待ちで停止しない）

- 既に受領している統合仕様書と以下のGoal詳細をもとに、P1〜P8の全実装・検証・必要Check Green・PR・Squash Mergeまで継続する。
- `DarumaPPAP/UnityAgent` と `DarumaPPAP/UnitySubAgentHub` は独立したRepository。Hub側への書込権限を必ず確認する。実行不能な権限不足があれば具体的に記録する。
- `backends` という新規Directoryは禁止。HubへRuntime / Policy / Approval / Resolver / auto-installを移してはならない。Main直push・force push・Release/tag発行は禁止。
- Unity Editor/実機がない場合は編集可能な成果物・CI基盤を完成させ、実機Gateだけ `BLOCKED_NOT_RUN` として報告する。
- 古いSource Lock/参照と新レイアウトが移行中に両立するようにConsumer先行互換→Hub移設→Pinned Source再pinを徹底する。

---

<!-- DOCUMENT_TYPE: EXECUTION_GOAL; NOT_IMPLEMENTATION_SPEC; REGENERATED_FOR_UNAMBIGUOUS_DELIVERY -->
# Codex Cloud Goal: UnityAgent / UnitySubAgentHub Repository Consolidation + Unity Compatibility CI — 全工程実装

あなたはCodex Cloudの `DarumaPPAP/UnityAgent` checkoutを起点に、以下2Repositoryのフォルダ構造・Source Lock・CI/Evidence・配布経路を**実際に修正し、テストし、PR・Merge・最終監査まで完遂**する実装担当者です。

**対象Repository:**
- `DarumaPPAP/UnityAgent`
- `DarumaPPAP/UnitySubAgentHub`

**最優先の方針:** `https://github.com/hatayama/unity-cli-loop` の安定したRoot構成、Unity世代別最小CI Project、限定互換テスト、将来Unity Canaries、Layout Contractを第一参考にする。`https://github.com/CoplayDev/unity-mcp` は実装責務分離の補助参照として使う。**`backends` という名前の新しいFolderや抽象Layerは絶対に作らない。**

このGoalは単なる調査・計画・MVP・1PR作成で終了する依頼ではない。全工程を完了するまで作業を継続する。ただし、権限・Unityライセンス・実Editor/実機Runnerなど外部必須条件が欠ける場合に合格を偽造してはならない。**実装完了と実測完了を区別**し、技術的に不可能な項目は再現可能なblockerを報告する。

開始時に添付仕様書 `UnityAgent_Repository_Consolidation_Spec_v1.md` が利用可能なら参照する。利用不可でもこのGoal本文と現在のRepository正本を元に実施する。古いチャット文脈より現在のmain、各Repoの`AGENTS.md`、Policy、Authority Map、Manifests、Source Lockを優先する。

## 0. Preflight（必須。編集前）

1. UnityAgent / UnitySubAgentHubの最新`main`を取得し、両SHA、default branch、open PR、rulesets/required checks、working tree、既存CI、Catalog Import、Release経路を記録する。`AGENTS.md`とPolicy承認境界を読み、現行の実パスを探索する。固定値を推測しない。
2. Codex CloudからUnitySubAgentHubを別checkout/worktreeとしてcloneでき、双方へbranch pushとPR作成・merge権限があるか確認する。なければCross-Repoの破壊的移設に着手せず、足りない接続・権限・具体的操作を`BLOCKED`として報告する。GitHub API閲覧可能とGit push可能は別。
3. Python3.12、`pip build/setuptools`、.NET8、PowerShell、npm、Git、`gh`、Unity Editor/License/Runner、GitHub Actionsを確認。Unityを起動できない場合は静的・host検証のみ実行し、Editor検証は`BLOCKED_NOT_RUN`。
4. 各RepoでReference Inventoryを作る。`rg`/`git grep` で全パス文字列、`__file__.parents`, import, `pyproject.toml`, CLI entry point, Unity GUID/meta, UPM local `file:` path, workflow trigger, manifests, snapshots, fixtures, release, installer、Knowledgeからの相対リンクを追跡。該当ファイルを網羅し、historical referenceとactive dependencyを区別。
5. 現行baselineを実行して結果を保存: UnityAgent `python Tools/validate_all.py` と`python -m build`/editable install/`unity-agent --help`、Hub `python Tests/Hub/validate_repository_authority.py`、`python Tests/Hub/validate_registry.py`、`python -m unittest discover -s Tests/Hub -p 'test_*.py' -v`、`python Tests/Hub/export_agent_snapshot.py --output <tmp>`、Artist `python Tests/Backend/verify_artist_backend_contract.py`、`python Tests/Compatibility/verify-unity-api-compatibility.py`、`dotnet build src/UnityArtist.Cli/UnityArtist.Cli.csproj --configuration Release`。必要依存がなければ導入し、外部条件不足と本来の不具合を区別。

## 1. Target — UnityAgent

最終的なRootは `.agents/`, `.github/`, `src/`, `Packages/`, `tests/`, `eval/`, `tools/`, `docs/`, `scripts/`、必要な実体がある場合のみ`ci/`、および必須Root設定ファイル。余計な空Folderは作らない。

`src/unityagent/`に `Context`, `ControlPlane`, `Operations`, `Orchestration`, `Persistence`, `Policy`, `Runtime` を移し、実装Python packageは小文字の`unityagent.*`へ移行する。`pyproject.toml` の `where=["src"]` と `[project.scripts] unity-agent = "unityagent.cli:main"` に変更し、旧`Tools/unity_agent_cli.py`のProduct実装を`src/unityagent/cli.py`へ移す。Runtime YAML/JSON、CLI metadata、installer、managed Control Plane、UPM bootstrap、Codex Plugin、Test/Eval/Workflow/Releaseの参照も移行する。

`Eval/` → `eval/`、全Layerに分散した`Tests/`を `tests/<domain>/` に集約する。`Tools/`はRepository検証用の`tools/`にし、Product CLI実装と混ぜない。現在の`Tools/validate_all.py`の検証coverage・CLI入口・CI check名を保ち、canonical entryを新パスに合わせる。

`Prompt/`は`Context/Prompt/Templates/`と内容/参照を照合し、重複ならactive callerを移した上で削除する。`SkillReferences/`は共有Standard→`docs/standards/`、Skill固有→`.agents/skills/<skill>/references/`へ。`Templates/`も参照を調査して`docs/templates/`/owning Skill/削除に振り分け。`Specs/`は機械契約→`src/unityagent/**/contracts/`、Human Docs→`docs/`へ。Authority MapはLayout Contractとは別の正本として残し、最終配置に移してValidator参照を同期する。

`EnvironmentSnapshot.myunitymcp`等の旧観測専用互換fieldはSchema/Probes/Fixture/Tests/contract versionを調査し、現行Consumerが不要なら撤去する。旧`MyUnityMcp` Runtime AdapterやLegacy 50 PORTを復活させない。Public依存が残る場合には適切な互換期間/移行策を設計し、根拠なく破壊しない。

絶対条件: **clean wheel installをcheckout以外のcwdで検証**し、`unity-agent --help` / `doctor` /代表的なCatalog/Policy commandsを実行できること。source treeからのテストだけで成功判定しない。`VERSION`、UPM、pyproject、Codex Pluginのmirrors、Windows PowerShell installer、`npm pack`、Releaseの全てを整合させる。

## 2. Target — UnitySubAgentHub

新しいRoot構造は `Hub/`, `Packages/`, `cli/`, `ci/`, `tests/`, `docs/`, `.agents/`, `.github/`、必要なRepository横断Tool/Scriptsのみ。

`Registry/`→`Hub/Registry/`; `Schemas/`→`Hub/Schemas/`; `SubAgents/`→`Hub/SubAgents/`; `Tests/Hub/`のValidator/Exporter→`Hub/Tools/`、Tests→`Hub/Tests/`; `Specs/repository-authority-map.yaml`→`Hub/repository-authority.yaml`; `Design/specialist-execution-admission.yaml`→`Hub/specialist-execution-admission.yaml`。Canonical `artist_subagent`等のIDsを変更しない。HubはMetadata/Contract/Snapshot only。Runtime/Policy/Approval/Resolver/Install機能は増設しない。

`Packages/com.darumappap.artist-subagent/` はUPM id/meta/GUIDを含め**維持**。`src/UnityArtist.Cli/`→`cli/artist/`へ移設し、.NET build、CLI entry、installer、tests、release、Unity Package/Manifestに埋め込まれたpathを全て更新。scriptsはOwnerを調べArtist専用ならCLI配下等に寄せ、Repository横断ならrootに残す。

`Tests/Compatibility/support-matrix.yaml`→`ci/compatibility/support-matrix.yaml`。各Evidence/Verifierを `ci/evidence/artist/{current,historical}` / `ci/verify/` へ用途別移設する。`Tests/Minimal`, `Tests/Backend`, CLI testsは実行責務に沿って分ける。Frozen Legacy 77 Tool inventory/tag/provenanceは`tests/fixtures/legacy/`へ無損失移動し、Git tag `v1.1.1`を書き換えない。`Design/`, `Specs/`, Root `MIGRATION_FROM_MYUNITYMCP.md`をdocsへ統合し、孤立`.meta`は本体/GUID依存を確認してから削除。

現在`TestProjects/UnityArtistVerification/`はUnity `6000.6.0f1` と`com.unity.pipeline 0.6.0-exp.1`を参照する。**内容を消さず** `ci/unity-projects/artist-e2e/`へ移す。`TestProjects/UnityArtistVerification-2022.3/`は`ci/unity-projects/historical/2022.3/`へ。2022.3を現行Supportに復活させない。

## 3. Cross-Repo Source Lock Migration（最優先の依存関係）

UnityAgent `Runtime/Distribution/subagent-sources.lock.json` はHub Full Commit SHAと旧 `Tests/Hub/export_agent_snapshot.py`、`Registry/subagents.yaml`、`SubAgents/artist_subagent/manifest.yaml`、`src/UnityArtist.Cli/...`をpinしている。Hub required CIもUnityAgent main Consumerのread-only `no_op`を期待する。単純renameしたHub PRを先にmergeしてはいけない。

この順で進める:

A. **UnityAgent側に旧/新Hub pathの明示的Dual-Read互換**を導入して検証・PR・GreenでSquash Merge。未知Source、hash改竄、non-matching commit、wrong identityは引き続きfail-closed。旧Pinned Hub commit検証も維持。

B. **Hub Catalogを移設**し、Source Ref/Schema/Tests/Export/CI全参照を更新。UnityAgent mainのConsumerとの読み取り互換がGreenになってからHub PRをSquash Merge。

C. **UnityAgent Lockを新Hub merge commit full SHAで再pin**し、Development / Pinned両方のImportを検証。Agent Release/workflow/fixturesを更新してPR GreenでMerge。

D. **Artist CLIやSupport Matrixも同じプロトコル**（Consumer新旧Path対応→Hub移設→Agent最終pin）で進める。

全PRは`main`から `chore/*` 等の既存許可prefixで作成。required checksのname、strict Contract、source hash、manifest checksを緩和しない。main直push / force push禁止。自動Mergeは必要Check Green、mergeable確認、既存Policyが許可する場合のみSquash。Release/tag publishは実行しない。

## 4. Unity CI/Editor Compatibility — `unity-cli-loop`方式を発展させる

`ci/unity-projects/`に **(i)現行Artist E2E Project、(ii)必要なUnity versionのMinimal Compile Fixture、(iii)Built-in/URP/HDRP Pipeline Fixture、(iv)historical fixture** を明確に分離して構築する。全version×全pipelineの総当たりをしない。Script/assembly/GUID/meta/local file package pathも検証対象。

Canonical full test: 正式に検証可能な現行EditorとPipelineで全部実施。New Unity minor/stream:最小compile/互換影響があるtestだけ。最新pre-release（例えば6000.7）はrelease Resolverで動的解決し、scheduled non-blocking Canaryで破壊的変更を検知。Unity License/Editor環境がなければ失敗を握りつぶさず`BLOCKED_NOT_RUN`にする。Unity Editor versionを推測で決めず、現行Project/Support Matrix/Unity公式API差分を突合する。

現行`Tests/Compatibility/support-matrix.yaml`はBuilt-in, URP, HDRPをUnity 6.x+ current primaryと宣言しているが、参照されたURP/HDRPの`UnityArtistVerification-URP`/`-HDRP`現行Fixtureはmainに見つからない。**Evidence YAMLだけで検証完了と判断しない。** 現実に再構築しEditorで検証できればcurrent evidenceへ、できなければhistorical + `not_observed`へ区分し、必要なRunner/License/Fixture手順を提示する。Built-inにも正式Fixtureとテストを用意する（空フォルダだけは不可）。

CIでは次を正しく分離:
- All-PR required: static schema/Hub snapshot/Agent import + host CLI/wheel/package contracts。
- Related-code PR: Unity version compile (Runner利用可能時)。変更検知はJob内で行いRequired checkをworkflow skipさせない。
- Scheduled/manual: Pipeline smoke、Rendering/Camera/Capture等のactual Editor E2E、latest prerelease Canary。
- Evidence: exact Unity Editor/Package/RenderPipeline, Project path, run id, input/output hashes, artifacts, stdout/stderr, limitationの記録。`pass`は実行したGateにのみ付す。

現行Artist Skillで `BASE`, `UNITY_6000_4`, `UNITY_6000_5`, `UNITY_6000_7` を固定している契約は根拠確認後に変更する。6.6を恣意的に新bucket化しない。Unity 6.5でのEntityId/API obsolete、RenderGraph、Rendering Debugger、SRP package差分は必要なfeatureに限定してテストする。

## 5. Documentation / Layout / Dead Code Cleanup

全active relative path、Markdown links、CI paths、branch triggers、installer references、tests、fixtures、manifest、PackageInfo/GUIDを再点検。`Specs/`、`Design/`、`Prompt/`、`SkillReferences/`、`Templates/`、`src/UnityArtist.Cli/`、Hub旧rootなどを実際に移動し、**旧rootにactive dependencyを残さない**。歴史資料はhistorical sourceとして保存してよいがcurrent authorityのように書かない。

`repository-layout.json`を2Repoに追加し、ValidatorとCIに接続する。root許可list・ownership・canonical path・禁止旧root・意図的例外を明示する。Authority Mapの正本性を潰さない。移動が全部終わる**最後のPhase**でstrict gateにする。現行Repoで使われる`.devcontainer`等の将来開発用Rootを誤って禁止しない。

## 6. 必須テストと受け入れ条件

**UnityAgent:** Canonical Validator全件、Golden/Regression/Runtime tests、`pip wheel` + clean venvからの実CLI起動、UPM npm pack、installer PowerShell構文、release path contract、version mirrors、Policy/Approval/Evidence安全契約。`src/unityagent` packageにResource YAML/JSONが含まれ、source checkout以外でも成功。

**Hub:** Registry + Manifest schema + snapshot export + authority + version mirrors、Artist CLI .NET build/tests、Unity API compatibility validators、frozen Legacy provenance、Consumer import `no_op`、`artist_subagent != unity_artist_cli`、optional/fail-closed。UPM ID/GUID/meta保存。

**Cross-Repo:** Source LockがHub最終merge SHA/full SHAと新pathを持ち、Development/Pinnedとも現在の結果に一致。双方のPR CI/Branch policy必須Checks Green。両mainの`git grep`で旧active path=0（historical例外を列挙）。旧Sourceの復元や緩いFallbackなし。

**Unity Editor:** Built-in/URP/HDRP fixtureと最小Smokeを実際にEditorで検証したときのみEditor PASS。UI上の`not_observed`/`unavailable`とCI内の`skipped`を成功にすり替えない。最小Fixtureがないときは作るか正式にblockして正直に報告。

**Git/PR:** 各段階は独立PRに分割し、毎回CIを見て原因を修正、GreenならSquash Merge。終わったbranchは削除し、最終的なmain構造・lock SHA・PR URLsを確認。CI停止を回避するためのskip化、required status改名、no-op空実装は禁止。

## 7. 実行継続ルール

- 先にPhase計画/issueを書いて終わらない。Preflightの後、実コード・Tests・CI・Docsを変更し続ける。
- 「とりあえずMVP」「Folderだけ移して後から直す」「既知FailureをTODO化して終了」は禁止。
- 不具合が出たらlog/traceから原因を特定し修正、確認を繰り返す。ただし同一PASSテストは不要に反復しない。
- セッション長・CI待ちを跨いでも一つのGoalを継続できるよう、各Phaseの開始/完了/PR URL/main SHA/未解決Gate/次の操作を `docs/migration/repository-consolidation-progress.md` に永続記録して更新する。再開時はその記録とGitHubの実状態を突合し、同じ変更を重複実行しない。
- 同時変更でCIとPinned Consumerが壊れる場合は、適切なDual-Read PR→Hub PR→Agent re-pin PRへ順序を戻す。
- 個別GitHub PRを作れない場合、勝手にFake PR URLを生成しない。アクセス権とブロッカーを明確化して安全に停止する。
- 最終レポートは静的/Host/Editor/Player/Visual/実機を分けて書く。未実施をPASSにしない。

## 8. 最終提出

Repository上に `docs/migration/repository-consolidation.md` を作成・更新し、before/after対応表、Decision、旧root削除一覧、Cross-Repo consumer/producers、CI matrix、Evidence、完了/Blockedの明細を記録する。

最後に日本語で次の情報を提出する:

1. 両Repositoryの最終Root tree、main commit SHA、Source LockがpinするHub full SHA。
2. 順番に実施した全PR/merge URL/commit、CI Check/Workflow結果。
3. UnityAgent clean-wheel CLI、Hub Registry/Artist CLI、Source Lock Development/Pinnedそれぞれの検証結果。
4. Unity 6+、Built-in/URP/HDRP、次期Canaryの実行済み/未実行の区別と、実Evidence/Artifacts。
5. 重複・不要ファイルの削除、History/Knowledge保存、残った意図的互換層と除去条件。
6. 外部条件不足なら `BLOCKED_NOT_RUN` の具体的原因、必要なUnity License/Windows runner/permissions、再実行コマンド。

**Goalの終了条件:** Code/CI/Docs/Cross-Repo Source Lock/PRまでの利用可能な全作業を終え、全検証結果と不足する外部Gateを偽りなく明示したこと。すべての必要な実Editor Gateが実行されない限り「フルE2E完了」とは呼ばない。