# Cohesion and File Granularity Standards

## Purpose

過剰な型・ファイル分割と、巨大な一枚岩の両方を防ぐ。ファイル数を最小化するのではなく、実装を理解・変更するために越える責務境界を最小化する。

`Single Cohesive Script First`は、小規模で単一の実行責務を持つ機能の既定である。複数の実行Phase、副作用、Failure Boundaryを一つの型へ押し込むための規則ではない。

## Symmetric review

新しいファイルにはSplit Reasonを要求する。同時に、複雑な責務を同一ファイルまたは同一Primary Typeへ保持する場合はKeep-Together Reasonを要求する。

### Split Reason

- ownerが異なる
- lifetimeが異なる
- dependencyまたはAssembly境界が異なる
- read-only解析とmutationの境界が異なる
- failure、retry、cancellation、rollbackの責任が異なる
- 独立テスト価値の高い複雑なロジック
- 独立した外部契約または置換可能Backend

### Keep-Together Reason

次をすべて説明できる場合に限り、複数の補助型または処理を同一Primary Typeへ保持できる。

- 同一owner
- 同一lifetime
- 同一execution phase
- 同一mutation boundary
- 同一failure boundary
- 主な変更理由が同じ
- 単独で理解または変更する価値が低い

「同じFeatureだけが使う」「publicではない」「ファイル数を増やしたくない」は単独ではKeep-Together Reasonにならない。

## Anti-monolith review triggers

次は自動分割条件ではない。責務、依存方向、Keep-Together Reasonを再評価するTriggerである。

- read-only解析とScene、Asset、Prefab、Project Settings等のmutationが同居する
- previewまたはplan作成と本生成が同居する
- UI stateとdomain resultまたはanalysis resultが同じ型に混在する
- Undo、Rollback、Asset保存、Folder作成を通常の解析ロジックが直接所有する
- 一つのPrimary Typeが検索、検証、計画、生成、永続化のうち3 Phase以上を所有する
- 一つのメソッドが複数のfailure boundaryまたはtransaction boundaryを所有する
- `Processor`、`Manager`、`Controller`、`System`等の広い名前へ無関係な責務が集約される
- Primary Typeへ到達する前に多数のtop-level補助型が並び、entry pointの発見を妨げる
- 一つの仕様変更で、独立Phaseを含むファイル全体の理解が必要になる
- Scene/Assetを変更しないロジックを単独検証できるのに、Unity Editor mutationへ密結合している

行数、型数、メソッド数は単独で分割理由にしない。ただし上記Triggerと同時に増大している場合は、肥大化のEvidenceとして扱う。

## Preferred boundaries

### Read-only analysis

- Source探索
- 入力検証
- Candidate作成
- Grouping
- Warning生成
- PreviewまたはPlan作成
- Stale検査

SceneとAssetを変更しないことを契約にする。

### Mutation / generation

- Scene Object生成
- AssetDatabase変更
- Undo Group
- Rollback
- Save / Refresh
- ProgressとCancellation

一つのtransaction boundaryとして所有する。

### Editor presentation

- EditorWindow UI
- Input state
- Result表示
- SceneView visualization
- Editor event subscription

解析結果そのものと、Foldout、選択、表示On/Off等の一時UI stateを区別する。

## Human readability gate

実装後に次を確認する。

- 新規参加者がentry pointと主要Phaseを短時間で発見できる
- ファイル名とPrimary Type名から責務と副作用を推測できる
- read-only経路とmutation経路が明確に分離されている
- 一つの変更で読む必要がある範囲が限定されている
- 非自明な制約、副作用、破綻条件に日本語コメントがある
- `Processor`等の広い名前を使用する場合、所有するPhaseと境界を明示できる

## Decision output

File Planでは各ファイルについて次を記録する。

- Primary Type
- Responsibility
- Owner
- Lifetime
- Execution Phase
- Side Effects
- Mutation Boundary
- Failure Boundary
- Primary Change Reasons
- Consumers
- Split Reason
- Keep-Together Reason

同一ファイルへ保持するFeature-local型についても、どのPrimary Typeに従属し、なぜ独立境界を持たないかを説明する。

## Example: Editor mesh generation tool

検索、Preview、Mesh Asset生成、Undo、Rollback、SceneView表示を持つEditor Toolでは、次を初期候補とする。

```text
FeatureWindow.cs
FeatureModels.cs
FeatureAnalyzer.cs
FeatureGenerator.cs
```

これは固定Templateではない。Analyzerが小規模ならWindowまたはGeneratorと統合できるが、read-only解析とScene/Asset mutationを統合する場合はKeep-Together Reasonを必須にする。
