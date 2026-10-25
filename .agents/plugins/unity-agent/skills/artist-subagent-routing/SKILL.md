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
