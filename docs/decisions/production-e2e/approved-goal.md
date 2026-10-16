# UnityAgent — Production E2E Integration Goal（Phase 0〜4）

## 最終Goal

UnityAgentの確定済み設計Decisionを現行コードへ実装し、**Unity 6.3 LTS（6000.3.x）＋URP**をG1検証基準として、以下をProduction Runtime上で成立させる。

- 複数SubAgentのTask協業
- Task別Acceptanceと制限付き自動修正
- Approval、Mutation Scope、Lease、Evidence、Checkpoint、Recovery
- QASubAgentによる検証・不具合切り分け
- WorldCreatorSubAgentによるBlender MCP経由の3D制作
- Blender → FBX → Unity Import → Prefab → Scene
- Stagingと安全なRollback
- Unity CLI Loop Hot ReloadによるC#修正高速化
- 通常CompileとHot Reloadの実測比較
- G2 / G3への段階的拡張

単なるPlan、Mock、Static Contractの成功をProduction E2Eの成功とみなさない。

**Unity Editor・Blender・ライセンス・GPU・対象デバイス等が利用できない場合は、実行していないGateを`BLOCKED_NOT_RUN`として記録する。**

Cloudで可能な実装、Fixture、Unit Test、Integration Test、CI、PR作成は継続して完了させる。環境不足を理由に、調査報告だけで作業を終了しない。

実装はPhase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4の依存順とする。

---

## 0. Repositoryと作業開始条件

### 正本Repository

https://github.com/DarumaPPAP/UnityAgent

参考Baseline：

`4747fd3f82e5a9c0be191d606f7827a16c8eef90`

これは以前に確認したSHAであり、常に最新とは限らない。

**作業開始時に必ず最新の`origin/main`、Open PR、既存CI、Definition Revisionを再確認すること。**

既にマージ済みの以下の変更を重複実装しない。

- PR #193：SubAgent配布統合、明示選出、Control Plane Project排他
- PR #194：Editor Play / Timeline動画Evidence

### 実装上の正本

- `AGENTS.md`
- `.github/branch-policy.json`
- `src/unityagent/policy/`
- `src/unityagent/contracts/`
- `src/unityagent/orchestration/`
- `src/unityagent/context/`
- `src/unityagent/runtime/`
- `src/unityagent/persistence/`
- `src/unityagent/operations/`
- `eval/`
- `subagent/`

既存のArchitecture、Contract、Naming、Coding Standardsを必ず確認する。

既存機能を再利用し、必要性が証明されない新しいFrameworkや独自基盤を追加しない。

---

## 1. 確定済みDecision

以下は承認済みの設計方針である。実装都合で変更しない。

### Core Architecture

- **UnityAgentが唯一のControl Plane**である。
- Policy、Approval、Orchestration、Runtime、Persistence、EvalのAuthorityを分離する。
- 4つのSubAgentを`subagent/`に同居させる。
- フォルダ名を`specialists`に変更しない。
- Mode概念・Mode UIを追加しない。
- SubAgentの自動選出とユーザー明示指定を両立する。
- 複数Taskは依存DAGと必要時の動的担当切替で協業する。
- Fast / Standard / OrchestratedをTask規模に応じて選ぶ。
- 小Taskに不要なGraph、Worktree、SubAgent、LLM呼び出しを発生させない。
- Unity CLIはAutomation入口、Unity Pipelineは接続中EditorへのBridgeとする。
- MCPをUnityAgent全体の必須依存にしない。

### Q-001〜Q-014

| Decision | 確定方針 |
|---|---|
| Q-001 | G0 Contract → G1独立Unity Fixture → G2実Project → G3 Player / Target Device |
| Q-002 | Development / Release分離。Developmentはレビュー済みCommit SHAを固定 |
| Q-003 | Trace → Attribution → Eval → ChangeProposal → 承認 → PR → Regression → Baseline比較 |
| Q-004 | Task DAG、段階的Scheduler、Project / Editor排他、必要時のWorktree |
| Q-005 B | 専門SubAgentがTask担当、QASubAgentが独立検証 |
| Q-006 | PerformanceSubAgentをQASubAgentへ再編。Performance分析能力を維持 |
| Q-008 B | Blender Pythonの制限付き操作と高リスク任意実行を分離 |
| Q-009 B | Task別Acceptanceと、Scope・予算内の制限付き自動修正 |
| Q-010 B | Staging優先、適用前差分固定、安全な限定Rollback |
| Q-011 B | Unity CLI Loop Hot ReloadをOptional Adapterとして追加 |
| Q-012 B | 外部BackendはDoctor自動、導入・更新は明示承認 |
| Q-013 B | Blender Session / Job / ResumeをUnityAgent Runtimeが管理 |
| Q-014 B | Blender → Staging → Artifact Manifest → Unity Editor Import |

**Blender MCP First**を維持する。

Q-007相当のBlender制作経路も上記の方針として扱う。外部生成Providerを黙って直接呼び出さない。

### 設計上の禁止事項

- 第二Control Planeの追加
- SubAgentごとの独立RuntimeやApproval管理
- Mode UIの追加
- 無断のPackage導入・更新
- 未承認の外部AI生成・課金
- 任意Python / C#を低リスクOperationへ偽装
- Raw `.unity` / `.prefab` / `.mat`の直接Mutationへの自動Fallback
- 実行していないGateをPASS扱いすること
- Unity Editor確認をPlayer / 実機確認と同一視すること
- Gitの破壊的復旧でユーザー変更を消すこと

---

# Phase 0 — 設計凍結・現行実装との差分監査

## 目的

確定DecisionをADR / Architectureへ保存し、現在のコードで何が実装済み・未実装・未検証なのかを明確にする。

## 実施内容

1. 最新`main`、Open PR、CI結果を再取得する。
2. PR #193・#194のマージ済み実装を確認する。
3. Q-001〜Q-014のDecisionを既存文書体系に合わせて正本化する。
4. 各機能を次の状態に分類する。
   - Implemented and Verified
   - Implemented but Unverified
   - Partially Implemented
   - Not Implemented
   - Superseded / Obsolete
5. 既存のTask Contract、Scheduler、Lease、Provider Registry、Setup / Doctor、Evidence、Checkpoint、Evalを監査する。
6. Plan-onlyの機能と実際のProduction Runtime実行を区別する。
7. 必要最小限の実装順序と回帰テストMatrixを作成する。

## 成果物

- Decision / ADR一覧
- Implementation Gap Matrix
- 現行Architecture図
- Phase別作業計画
- 変更対象ファイル一覧
- Regression / Acceptance Matrix

Phase 0の文書化だけで全体GoalをCompleteとしない。

---

# Phase 1 — Control PlaneとE2E Runtime基盤

## Task Ownership

Taskに以下を関連付ける。

- Task ID / Run ID
- Goalと対象Scope
- Task依存関係
- 担当SubAgentとHandoff履歴
- Project / Definition Revision
- 必須Acceptance Gate
- Approval / Mutation Scope
- Budget / Retry
- Evidence
- Failure Attribution
- 最終判定

既存のTask ContractとState / Persistenceを利用し、重複する管理基盤を作らない。

## Task DAGとRuntime

既存のAdaptive ExecutionおよびDAG Plannerを監査し、plan-onlyの判断を実Runtimeへ接続する。

実行権限はControl PlaneとRuntime Guardが所有する。

依存Taskが完了していない場合は実行しない。

同じUnity Projectを変更するTaskは安全な排他制御を維持する。

独立Taskは必要に応じて並列化する。ただし並列効果は実測する。

## Acceptance / QA

Task開始時にRequired Gateを確定する。

QAが都合よく必須Gateを削除したり、未観測結果をPASSへ変更したりできないこと。

次を区別する。

- Passed / Verified
- Failed
- Unavailable / Blocked
- Inconclusive / Not Observed

Taskの作業結果を報告できても、必須Gateが未検証ならVerifiedにはしない。

## Retry / Recovery

インフラRetryと専門SubAgentによる意味的修正Retryを分離する。

既存のRetry Budget、Semantic Loop、Failure Attributionを再利用する。

初期値として同一Taskの意味的修正は最大2回を候補とする。ただし既存Contractと実測結果で調整し、根拠なく固定しない。

無限再試行、同じ失敗への無意味な再実行、外部APIの二重課金を防ぐ。

## Evidence / Checkpoint

Runtimeが観測した結果をPersistenceに保存し、Task・Revision・Approvalと対応付ける。

CheckpointでRunを復元してもUnity Asset自体は復旧しないことを明確にする。

中断後はRevisionと外部副作用を照合してからResumeする。

## Staging / Rollback

適用前に以下を記録する。

- 対象AssetとPath
- 変更前Hash
- `.meta`とGUID
- 生成物Hash
- Mutation Scope
- 承認情報
- Restore / Rollback手順

ほかのユーザーやProcessによる変更がある場合は自動上書きしない。

## Lease

PR #193のControl Plane Project排他と、既存Runtime Leaseの責任範囲を監査する。

二重LockやDeadlockを追加しない。

Unity Editorの手動操作、別Process、別Worktree、Unity自身のProject Lockを考慮する。

Stale Leaseを根拠なく自動奪取しない。

## 必須回帰テスト

- Fast Pathの低Overhead
- Task DAGの依存順
- SubAgent明示選出・自動選出
- Task担当切替
- Policy・Approval・Scope拒否
- Retry / Budget上限
- Evidence不足時の停止
- 中断／Resume
- Revision不一致
- Project Lease競合
- 安全なRollback
- 失敗時のFail-Closed

---

# Phase 2 — SubAgentとBackend統合

## 2-1. QASubAgent

PerformanceSubAgentをQASubAgentへ再編する。

既存のPerformance分析、Profiler観測、Performance Regressionの機能は維持する。

追加する役割：

- テスト計画
- 不具合再現
- Failure Attribution
- Acceptance判定補助
- Regression評価
- 必要な修正候補の提示
- 修正後の再検証

古い`performance_subagent`参照をManifest、Catalog、Route、Context、Contract、Eval、Testから監査する。

互換が必要なIDは明示的な移行処理を用意する。

QAがSubAgentを直接Dispatchしない。Orchestrationが担当切替を決定する。

## 2-2. WorldCreatorSubAgent

既存の`world.plan`を維持しつつ、Blender MCPによる実3D制作能力を追加する。

対象：

- Blender Scene観測
- Mesh制作・編集
- UV / Material調整
- 生成Job管理
- FBX Export
- Artifact検査
- Unity ImportへのHandoff

Blender MCP Firstを維持する。

初期E2Eでは外部有料生成を利用せず、決定的な手順で岩モデルを作成する。

Blender Pythonは型付きCapabilityまたはレビュー済みTemplateを優先し、任意Pythonを既存Policyの`arbitrary_code`禁止から迂回させない。

## 2-3. Blender Session / Job

以下を管理する。

- Session identity
- Blender / Addon / MCP Protocol Version
- Session排他
- Job Handle
- 生成Request Digest
- Approval / Budget
- Job Status
- Artifact Hash
- Evidence / Resume

外部生成がTimeoutしても、生成が失敗したと決めつけて同じJobを再送しない。

Blender MCPの内部Pending機構を再利用しつつ、UnityAgent側でもTaskとの対応を記録する。

生成待機中にUnity Project Leaseを長時間保持しない。

生成完了時のBlender Scene Importは副作用として扱う。

## 2-4. Optional Backend / Setup

既存Setup / Doctorに以下を追加する。

- Blender MCP
- Unity CLI Loop

検出項目：

- 導入状態
- Executable / Package Version
- Project Binding
- Protocol互換
- 実行Capability
- Revision整合
- 接続状態

Setupは次の経路を維持する。

`Doctor → Setup Plan → Approval → Apply → Doctor`

インストールや更新は明示承認が必要。

未導入でもUnityAgent全体を停止せず、利用できないCapabilityのみUnavailableとする。

---

# Phase 3 — Unity 6.3実E2E

## 検証Project

独立したG1専用Fixtureを使う。

- Unity 6.3 LTS（6000.3.x）
- Unity Patch Version固定
- URP
- RenderGraph有効
- Windows Editor優先
- Packages / ProjectSettingsをGit管理
- 機密ゲームAssetを使用しない

## 必須E2Eシナリオ

UnityAgentへ次のGoalを渡す。

**「岩の3Dモデルを1個制作し、Unity Projectへ取り込み、Prefab化してSceneへ配置し、品質検証を完了してください。」**

実際に次の処理を実行する。

1. UnityAgentがGoal・Scope・Approval・Acceptanceを決定する。
2. WorldCreatorSubAgentを選出する。
3. Blender MCPの状態、Session、Capabilityを検査する。
4. Blenderで岩Meshを制作する。
5. FBXへExportする。
6. Stagingへ保存する。
7. Artifact Manifest、File Hash、Geometry、Scale、Texture依存を検査する。
8. UnityAgent RuntimeがProject Leaseを取得する。
9. 承認済みEditor経路でUnityへImportする。
10. ModelImporter、Material、Shaderを確認する。
11. Prefabを作成する。
12. Sceneへ配置する。
13. Compile / Import / Missing Reference / Visualを検証する。
14. QAが問題を検出した場合、必要なSubAgentへTaskを戻して再検証する。
15. 再Export・再ImportでGUIDとPrefab参照を維持できることを確認する。
16. 故意の失敗でRollbackを検証する。
17. 競合時は自動復旧せず、安全に停止する。
18. Required GateがPASSした場合のみVerifiedとする。

## PR #194の実Unity検証

マージ済みのPlay / Timeline動画Evidenceも必要に応じて検証する。

確認項目：

- Unity 6.3でのEditor Compile
- Game View Screenshot
- MP4録画
- 録画ファイルのデコード
- Camera / UI / URP描画
- Timeline再生
- Play中断・Domain Reload時の終了処理
- Evidenceと実際の映像の整合

録画ファイルが生成されたことだけでVisual AcceptanceをPASSとしない。

## 実行環境不足の場合

Cloud環境にUnity Editor、Blender GUI、ライセンス、必要なGraphics環境がなければ、利用可能なWindows Self-hosted Runner等の実行経路を整備する。

利用可能なRunnerや認証情報が存在しない場合、それを捏造・回避せず、未実行Gateを`BLOCKED_NOT_RUN`として記録する。

実行可能なコード・Fixture・Test・CI・PRは作成する。

---

# Phase 4 — Hot Reload・性能測定・G2/G3

## 4-1. Unity CLI Loop Hot Reload

Unity CLI Loop V3をOptional Adapterとして追加する。

新Capability案：

`editor.hot_reload`

既存Unity CLI / Pipeline Providerを置き換えない。

実行フロー：

1. 承認済みSource Patch
2. Editor / Project Binding検証
3. Hot Reload適用
4. Patch結果確認
5. Play状態で動作検証
6. 必要に応じて修正
7. 通常Compile
8. QA Acceptance

部分適用・Skipped・Failedを成功扱いしない。

Hot Reloadで差し替えたコードを元に戻しても、ソース変更や実行中の副作用が復旧するとは限らないため、Q-010のRollbackとは区別する。

## 4-2. Baseline比較

同じ変更Taskを、以下の2条件で比較する。

- 通常Compileのみ
- Hot Reload利用

実測項目：

- Latency
- Median / p95
- Task完了率
- Retry回数
- Token消費量
- Play状態再現の手間
- Fallback回数
- Runtime副作用
- Regression発生率

Tokenの実測値が取得できない場合は`unmeasured`と記録する。

改善が確認できない場合、Hot Reloadを常時利用にしない。

## 4-3. G2 / G3

G2では許可された実ゲームProjectで統合検証する。

G3では対象Player・Target Deviceで検証する。

Compile、Editor、Player、Visual、Performance、実機を別々のEvidenceとして扱う。

Switch / PS5 / PS4等のSDK、ライセンス、機密Assetは、必要な承認と実行環境がなければ取得しない。

---

# Git / PR運用

- `main`から既存規約に沿った短命Branchで作業する。
- 変更は依存関係ごとにレビュー可能なPRへ分割する。
- PRを積み重ねる場合、依存関係とBaseline Commitを明記する。
- PhaseごとにUnit / Integration / Regression Testを実施する。
- CI Greenと実Unity E2E Greenを区別する。
- 既存機能との重複や古い契約を残さない。
- `main`への直接Commitは禁止。
- 新規PR作成は実施してよい。
- **新規PRのMerge、Release、Tag作成、Repository Archive、破壊的削除は明示指示なしでは実施しない。**

設計Decisionを変更する必要が生じた場合は、変更理由、代替案、効果、保守コスト、リスクを整理し、ユーザーの判断を求める。

---

# 最終Acceptance

| Phase | 完了条件 |
|---|---|
| Phase 0 | Decision正本化、Implementation Gap Matrix、実装計画が完成 |
| Phase 1 | Task DAG / Ownership / Acceptance / Retry / Evidence / Staging / LeaseがRuntimeで機能 |
| Phase 2 | QASubAgent、WorldCreator、Blender MCP、Optional Backend Setupが接続 |
| Phase 3 | 実Unity 6.3でBlender → FBX → Import → Prefab → Scene → QA → Rollbackが成功 |
| Phase 4 | Hot Reload実測比較が完成し、G2/G3の状態が明示される |

## 最終報告形式

各Phaseについて次を報告する。

- 実装内容
- 変更ファイル
- PR URL
- Commit SHA
- 実行したテスト
- CI結果
- Unity Editor / Blender / Player / Target Deviceの実測Evidence
- 未実行Gate
- 既知の不具合
- 未解決Risk
- Latency / Token測定結果
- Baselineとの差異
- 次に必要な操作

**Required Gateが未観測の場合、全体GoalをCompleteと報告してはならない。**

環境によるBlockが発生しても、実行可能なPhaseの実装・Test・PR作成を継続する。

目的は書類を完成させることではなく、UnityAgentのProduction E2E能力を実際に成立させ、その証拠を残すことである。