---
name: artist-subagent-routing
description: Use when a Unity visual-art, lookdev, lighting, environment, camera, capture, evaluation, refinement, Timeline, or cinematic task needs specialist planning through the optional ArtistSubAgent.
---

# ArtistSubAgentへの委譲

専門Agentの正本IDは `artist_subagent`、実行Backendは `unity_cli` です。既存UnityAgent Control Planeを入口とし、公式Unity CLI／Pipelineから任意導入のArtist UPMへ接続します。

## 選出と実行

1. 利用者の意図からProviderに依存しないCapabilityRequestとdomain／workflowを決めます。
2. `src/unityagent/runtime/reference_implementation/subagent-catalog.yaml` から専門Profileを選出し、現在のProjectに対するActivation Factを確認します。
3. Artist Package、互換性、Project binding、Pipeline到達性のいずれかがfalse／unknownなら候補から除外します。Capability解決のための自動Installは行いません。
4. 既存Context AssemblyでProject／Runに束縛したContextを構築し、PolicyとScopeを検証します。新しいScopeやdomainには新しいRunを使います。
5. Runtime Tool Brokerが `unity_cli` を選出し、型付き操作を実行します。UI／Codex／Task GraphからProviderやEditor Pipelineを直接呼び出して承認を迂回しません。
6. Editor応答を検証し、Persistenceへappendした結果だけをdurable Evidenceとして報告します。

`Entry → Control Plane → Policy / Context / ArtistSubAgent選出 → Tool Broker → unity_cli → Unity Pipeline → Artist UPM → 結果検証 → 永続Evidence`

既存Entryの `uagent artist` は `inspect`、`plan`、`preview`、`apply`、`capture`、`evaluate`、`refine`、`history`、`cinematic` の全9コマンドを扱います。Cinematicのoperationは `inspect`／`plan`／`preview`／`apply` です。入力は既存CLI helpと `subagent/artist_subagent/contracts/backend-surface-contract.yaml` を確認します。

## 承認と結果の境界

- Plan／Previewは変更の成功ではありません。Editorが返したExact Diff、Revision、実変更先 `mutationPaths`、Project／Run／ContextをControl Planeの計画へ束縛します。
- Mutationは明示的な `uagent artist approve` と一致する承認参照を必要とします。TokenやContextを呼出し側で作りません。Editorは実行直前に同じ承認Storeを照合し、取消、期限、差分／Revision／Scopeの不一致、再利用を拒否します。
- `capture` は明示したCameraと実ファイルを観測します。Captureの生成やハッシュを、人間の視覚承認として扱いません。
- `evaluate` はCaptureとReview decisionを束縛した計画を作り、明示承認後にReviewを記録します。未承認の計画だけでhuman acceptanceを発行しません。`refine` は同じRun／ContextのEvaluationへ接続します。
- CLI外側の成功だけでEditor成功と判断しません。内側の失敗、欠落Receipt、未保存、Undo、Evidenceの状態を保持します。自動Saveを行いません。

## 任意導入と報告

Artist UPMの製品IDは `artist_subagent`、Package IDは `com.darumappap.artist-subagent` です。明示的なSetupは既存の `doctor → setup plan → approval → setup apply → doctor` に従います。独立Artist Hostと別Artist Codex Pluginは必要ありません。

出力には意味的Capability、qualifiers、`profile_id=artist_subagent`、選出済みBackendの `provider_id=unity_cli`、観測Fact、承認／Scope／Revision、Evidence参照を記載します。未実行のGateは `BLOCKED_NOT_RUN`、未観測は `not_observed` とし、Compile、Editor、Player、Human Visual Acceptanceを区別します。

一般的なProject、Hierarchy、Compile、Test、Build、Play／Stop、Log、UI、Audio、Addressables操作はArtistSubAgentの責務に追加しません。未知のActivation Factをtrueへ補完せず、未導入のArtistを要求充足のためにInstallしません。

## Output Contract

- 選出結果には意味的Capabilityとqualifiers、`profile_id=artist_subagent`、`provider_id=unity_cli`、対象Project、Run、Context参照、Package互換性とPipeline到達性の観測根拠を含めます。不明なFactは不明のまま報告します。
- Mutation結果にはControl Planeが管理するPlan／Approval参照、承認Scope、実行時Revision、Exact Diff、`mutationPaths`、保存有無、失敗時のUndo結果を含めます。Policyは承認要否、Control Planeは承認と実行境界を管理し、Artistは独自の承認を発行しません。
- EvidenceはPersistenceへのappendと整合性確認を終えた参照を返します。Editor応答だけの結果、部分的な実行、通信断、Undo失敗、Evidence欠落を成功へ変換しません。Compile、Editor、Player、実機、Human Visual Acceptance、Performanceの判定は個別に記録します。

## Checklist

- [ ] 正本CatalogでArtistSubAgentの導入、互換性、Project binding、Pipeline到達性を実測し、既存Context AssemblyのProject／Run／Scopeへの束縛を確認した。
- [ ] EntryからControl Plane、Policy／Context、Tool Broker、`unity_cli`、Unity Pipeline、Artist UPMを通り、直接Mutationや旧HostへのFallbackを使っていない。
- [ ] Mutation前に承認参照、期限／取消、Revision、Exact Diff、Scope、単回消費を照合し、失敗したMutationを無条件に再実行していない。
- [ ] Apply後の実状態、変更先、保存禁止条件と必要なUndoを確認し、成功・失敗双方のEvidenceをPersistenceで検証した。
- [ ] 未実行Gateと未観測Gateを明示し、Capture生成を人間の視覚承認として報告していない。

## Common Mistakes

- `unity_artist_cli` や独立Artist Hostを実行Providerとして復活させること。全9コマンドは `unity_cli` を使い、旧IDのSnapshot・Receiptを受理せず、新規実行経路へ戻しません。
- Discoveryのunknownをtrueに補完したり、Package欠落時に自動Installしたりすること。既存Setupの明示的な計画・承認・適用契約を使います。
- 呼出し側でToken／Contextを作成し、Editor Pipelineへ直接Mutationを送ること。Control Planeの承認Authorityと既存Context Assemblyを維持します。
- Plan／PreviewやCLI外側の成功をApply成功とみなすこと。Editor内部結果、実状態、Revision／Exact Diff、永続Evidenceを照合します。
- 通信断や実行失敗で消費済み承認を未使用へ戻し、Mutationを再送すること。承認の消費状態を保持し、観測した失敗とUndo結果を記録します。
