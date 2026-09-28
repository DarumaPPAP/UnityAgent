# Specialist Productionization Implementation Plan

**Goal:** Graphics / Performance / WorldCreator のProduction契約、Content Pilot、Legacy回収、利用可能なRuntime検証を両Repositoryで完成させる。

**Architecture:** UnityAgentが唯一のControl Plane。Semantic reasoningは既存CodexRunner、観測はToolBroker、永続EvidenceはPersistenceが所有する。Hubは実行方式を含む静的Manifestを所有する。

**Tech Stack:** Python、YAML、JSON Schema、既存CodexRunner / Unity Pipeline。

**Spec:** ユーザー指定 `c4f9d691-1498-47b9-a546-ee7fb6b8b512/pasted-text-1.txt`（Goal全体。任意Runtimeの未評価とLegacy Evidence blockerは正当な結果）。

## Global Constraints

- Fake Provider、Specialist固有Generic分岐、Silent fallback、未観測Evidenceの昇格は禁止。
- Artist互換性とCandidate fixtureを維持。旧Schemaは明示Versionで検証。
- Content昇格判断はHuman Review。Legacyはparity / runtime Evidence不足なら保持。
- CI Green、mergeable、behind=0、blocking findingなしを確認してHub→UnityAgentの順でMerge。

## Review Focus

- Reasoningへprovider_idを注入した入力をSchema / Import / Runtimeで拒否する。
- 観測が欠ける場合は未知を維持し、PerformanceのCPU/GPU分類を捏造しない。
- Context fingerprint、観測Evidence、生成Artifactの対応が崩れた結果を拒否する。
- ContentのProject Decisionをglobal defaultへ持ち上げず、Applyには承認とexact diffを要求する。
- Legacyの履歴参照とactive依存を分離し、REPLACEDには実装・呼出元移行・必要Evidenceを要求する。

## Task 1: Architecture reconciliation / admission（指示0–22）

- [x] Hub `Design/specialist-expansion-architecture.md` のRuntime Authorityを現行実装へ修正。
- [x] `Design/specialist-execution-admission.yaml` にProvider Registryの調査根拠と3体の実行方式を保存。
- [x] Admissionの型・Capability・Provider非混同をHub testとUnityAgent cross-repo fixtureで検証。

## Task 2: Production contracts（指示23–40）

- [x] Hub `Schemas/subagent-manifest.schema.json` をv5、Snapshotをv3へ明示移行。Artistもexecution.kindを宣言。
- [x] `Tests/Hub/validate_registry.py` / exporterで条件付きBackend契約を検証。
- [x] UnityAgent `profiles.py` / `catalog_import_gate.py` へ明示vNext契約とPinned Schemaを追加。
- [x] 不正なreasoning+provider、provider欠落、旧版の暗黙変換、Artist回帰をテスト。

## Task 3: Specialist promotion / integration（指示41–67）

- [ ] Hub ManifestとUA Consumer ProfileをAdmissionに従い追加。
- [ ] Graphics / PerformanceのInstructions / Output Contract / domain validationを追加。
- [ ] Generic ReasoningOutputErrorを境界とし、既存Handoff / CodexRunner / Evidenceを利用。
- [ ] Entry→観測→Context→reasoning→検証→Persistenceの3体E2E、曖昧Routing、無Mutationを検証。

## Task 4: Content / Legacy（指示68–92）

- [ ] Texture、Audio、Addressablesの既存機能を監査し、Skillとdeterministic Analyze / Planを実装・検証。
- [ ] 指定metricsを計測してContentのHuman Review判断を取得。
- [ ] Legacy 77件のowner / replacement / caller / test / documentation / Evidenceを実際のファイルで照合。
- [ ] KNOWLEDGEを回収しRETIREのactive参照を除去、PORTの未完了は具体的Evidence blockerを記録。
- [ ] Repository-wide依存scanを実装し、撤去条件を満たした場合だけdetach。

## Task 5: Evidence / publication（指示93–140）

- [ ] Environment discovery、利用可能なCompile / Editor / Player / Device / Reasoning / Performance / Visualを検証。
- [ ] Graphics 6領域、Performance 6領域、WorldCreator 5領域のA/B/Cと全metricsを記録。未評価は明記。
- [ ] Architecture / README / specialist / migration文書を更新しdead contractを検索。
- [ ] `Tools/validate_all.py`、Hub registry / unit tests / snapshot、clean checkoutを実行。
- [ ] 少数PRへまとめ、CIとReviewを確認して依存順にMerge。mainの最終状態を指示全項目と照合。

## 実装チェックポイント（2026-09-27）

Phase 0/1とvNext契約基盤を実装済み。Production CatalogのArtist以外の登録、Graphics / Performance artifact、観測EvidenceのContextへの接続、Content、Legacy回収、Environment discovery、A/B/C、PR/CI/Mergeは未完了。

- UnityAgent base: `e388f19011d432513daed8d25b394a4e3019b27a`
- Hub base: `67e8aa10b89fe587476e9091cd7e5139449ca2cf`
- 両方 `feat/specialist-productionization`。既存checkoutを再利用。
- `Tools/validate_all.py`: PASS、Runtime 329 tests（2 skips）。Hub registry PASS、Hub 31 tests PASS。
- `profiler.observe` の唯一の宣言はProduction無効の `myunitymcp`。Admissionの `production_observation_gaps` に記録。要件削減やLegacy再有効化は禁止。
- Profile v3のreasoningはexecutionとselectionを明示。Hub instruction/output参照とローカル参照は `hub_contract_refs` で対応付け、Import Gateで照合。
- Candidate契約は維持。Production Resolverは同じ検証済みContext判定を利用し、Control Planeは選出結果から汎用reasoning Handoffを作る。
- 2026-09-28: 読取観測payloadのimmutable保存、durable EvidenceのRun / Project / Capability / digest照合、既存Context AssemblyによるBudget / Fingerprint更新、Reasoning Handoff再生成を実装。実ToolBrokerとcontrolled Codex processのfixtureで接続を検証。必須観測の欠落とBudget超過を遮断。
- 同変更の `Tools/validate_all.py`: PASS、Runtime 333 tests（2 skips）、Context 34、Orchestration 35、Eval 74、Persistence 19。Live Runtimeの検証ではない。
- 次の必須実装: Graphics / PerformanceのInstructions・Output Contract・validatorとProduction Profile、Hub Manifest登録。Performanceの `profiler.observe` Production観測Surface不足は引き続き未解決。
- 現在のProduction catalogはv1のArtistのみであり、Profile v3対応を追加しただけ。3体の登録完了・Production Verifiedは宣言しない。

## 現在の作業状態（2026-09-28、上記履歴を更新）

- Graphics / WorldCreatorのHub Manifest v5、Consumer Catalog v3、Production route bindingを作業ブランチに追加。PerformanceはProductionのprofiler.observe不足のため未登録。
- Graphics / PerformanceのInstructions、Output schema、allowlisted domain validatorを追加。WorldCreatorの既存Artifact validatorを維持。
- 観測前Activation `activated` と観測後Context `selected` を分離。Graphicsの本番Catalogから実ToolBroker・Source FileProvider・Persistence・Context再構築・controlled Codex processまでのfixtureを追加。unknown PipelineはReasoning前に停止。
- Rendering初期分析と再現検証/ApplyのContext要求を分離。条件付き `required_when_active` で従来の追加Bindingを必須化。
- Hub Production Snapshotを固定fixtureへexportし、現行Consumerとのno-op importと観測要件drift拒否をテスト。
- 未完了: 実Projectのdeterministic project.inspect/Render Pipeline観測とHost executor接続の確認、Live環境調査、Content、Legacy実回収、A/B/C、最終docs、PR/CI/Merge。現在のfixtureはLive ReasoningやProduction Verifiedの証拠ではない。

### 2026-09-29追記

- FileProviderの `project.inspect` を実装。Serialized Project設定とQualityごとのOverrideを確認し、Built-in/URP/HDRPが一意に判定できない場合はunknown。実Editorのactive qualityは主張しない。
- Host CLIにEntry v2のread-only `run --request` 経路を追加。File Providerで `project.inspect` / 明示対象の `source.read` を既存ToolBroker経由で実行する。HostからModelを選べない場合はrunner_unavailableを返す。
- 実Projectの特定は未完了。Windowsのprocess CommandLine取得はアクセス拒否。特定のProjectを他のProjectとして代用しない。
