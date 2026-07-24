# StageLightingExchangeSystem 実装Plan

- FeatureName: `StageLightingExchangeSystem`
- Status: Implemented
- LastUpdated: 2026-07-24

## 1. 実装境界

Stage Sceneのロード検知、登録判定、Active Scene切り替え、Environment適用、Editor自動同期、Light Probe再四面体化を実装する。

Player実行中のLighting Data Asset直接交換と独自Lightmap配列管理は行わない。

## 2. ファイル構成

```text
Implementation/StageLightingExchangeSystem/
├─ README.md
├─ Runtime/
│  ├─ AssemblyInfo.cs
│  ├─ StageLighting.asmdef
│  ├─ StageLightingData.cs
│  └─ StageLightingExchangeSystem.cs
└─ Editor/
   ├─ StageLighting.Editor.asmdef
   ├─ StageLightingDataEditor.cs
   └─ StageLightingDataSynchronizer.cs
```

## 3. 責務

### StageLightingData

- Stage Scene識別情報を保持する。
- Environment Snapshotを保持する。
- EditorでLighting SettingsとLighting Data Assetを保持する。
- RuntimeのScene検索を提供する。

### StageLightingExchangeSystem

- `SceneManager.sceneLoaded`を購読する。
- 登録済みSceneだけを適用する。
- SceneをActive Sceneへ変更する。
- EnvironmentとAmbient Probe更新を実行する。
- Light Probe再四面体化要求を同一フレーム内でまとめる。

### StageLightingDataSynchronizer

- Scene保存、Lighting更新、Bake完了を監視する。
- 対象Sceneを一時的にActive Sceneへ変更してRenderSettingsを取得する。
- 元のActive Sceneを必ず復元する。
- 変更があるDataだけをDirty化して保存する。

### StageLightingDataEditor

- 自動同期状態を説明する。
- アクティブScene同期、一括同期、DataからSceneへの適用を提供する。

## 4. 適用順

```text
Stage Scene Load
    ↓
StageLightingData.TryGetEntry
    ↓ 未登録
return
    ↓ 登録済み
SceneManager.SetActiveScene
    ↓
StageEnvironmentSettings.Apply
    ↓
DynamicGI.UpdateEnvironment
```

Light ProbeはSceneロードイベントではなく`LightProbes.needsRetetrahedralization`通知を起点にする。

## 5. 互換性

- Namespaceは`StageLighting`とする。
- Runtime / Editorでnamespace階層を増やさない。
- Runtime Assembly名は`StageLighting`とする。
- Editor Assembly名は`StageLighting.Editor`とする。
- Serialized fieldは初版のためMigrationを持たない。
- mutable static runtime状態、Singleton、Service Locatorを追加しない。

## 6. 検証

### 静的確認

- RuntimeコードのUnityEditor参照が`UNITY_EDITOR`条件内に限定されていること。
- Sceneイベントを`OnDisable`で解除すること。
- Scene Path優先と同名Scene拒否が実装されていること。
- Active Sceneを変更したEditor同期処理がfinallyで元へ戻すこと。
- Namespace placeholderが残っていないこと。

### Unity側確認

- Unity 6000.3でRuntime / Editor Assemblyをコンパイルする。
- StageLightingDataを作成してSceneを登録する。
- BakeとScene保存後に参照が自動更新されることを確認する。
- Additive Loadした登録StageがActive Sceneになることを確認する。
- 未登録Sceneロード時に処理されないことを確認する。
- Player / IL2CPPでUnityEditor参照エラーがないことを確認する。

## 7. Rollback

`Implementation/StageLightingExchangeSystem`と`Specs/StageLightingExchangeSystem`を削除し、Bootstrap Sceneから`StageLightingExchangeSystem`を外す。
