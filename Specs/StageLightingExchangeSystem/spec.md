# StageLightingExchangeSystem 要件定義・仕様書

- FeatureName: `StageLightingExchangeSystem`
- DocumentVersion: `1.0.0`
- Status: Implemented
- SpecPath: `Specs/StageLightingExchangeSystem/spec.md`
- LastVerified: 2026-07-24

## 1. 目的

Bootstrap Sceneを常駐させるマルチシーン構成で、Stage Sceneのロードを検知し、登録済みStageだけをLightingの使用元へ切り替える。

StageごとのEnvironment、Lighting Settings、Lighting Data Assetを`StageLightingData`で管理し、Scene保存またはLighting更新時にDataを自動同期する。

## 2. 対象環境

- Unity: `6000.3`
- Render Pipeline: 非依存
- URP: `17+`で利用可能
- Player: Mono / IL2CPP
- Primary Platform: Nintendo Switch
- Namespace: `StageLighting`
- Runtime Assembly: `StageLighting`
- Editor Assembly: `StageLighting.Editor`

## 3. 機能要件

### FR-001 Stage登録

`StageLightingData`は複数のStage Sceneを登録できる。

各Entryは次を保持する。

- Scene Asset
- Scene GUID
- Scene Path
- Scene Name
- Lighting Settings
- Lighting Data Asset
- Environment

### FR-002 Sceneロード検知

`StageLightingExchangeSystem`は`SceneManager.sceneLoaded`を購読する。

ロードされたSceneがDataへ登録されていない場合は処理しない。

### FR-003 Lighting切り替え

登録済みSceneがロードされた場合、次の順で処理する。

1. SceneをActive Sceneへ変更する。
2. Entryに保存されたEnvironmentを`RenderSettings`へ適用する。
3. `DynamicGI.UpdateEnvironment()`を実行する。

Lighting Data AssetはPlayer実行中に直接変更しない。Editorで対象Sceneへ割り当て、Sceneロード時にUnityが反映したデータを使用する。

### FR-004 起動済みScene検出

`StageLightingExchangeSystem.Start`時に、すでにロード済みの登録Stageを一度だけ検索する。

Active Sceneが登録済みならそのSceneを優先する。未登録の場合はロード順の末尾から登録Stageを検索する。

### FR-005 Environment管理

Environmentは次を保持・適用する。

- Skybox Material
- Ambient Mode
- Ambient Sky / Equator / Ground / Flat Color
- Ambient Intensity
- Default Reflection Mode
- Custom Reflection Texture
- Default Reflection Resolution
- Reflection Intensity / Bounces
- Fog Enabled / Mode / Color / Density / Start / End
- Subtractive Shadow Color
- Halo Strength
- Flare Strength / Fade Speed

Scene Object参照であるSun SourceはDataへ複製しない。Active Scene変更後にScene自身が保持する参照を使用する。

### FR-006 Editor自動同期

次のタイミングで、ロード済み登録SceneからDataへ同期する。

- Scene保存後
- Lighting Data更新後
- Lighting Bake完了後

同期対象はEnvironment、Lighting Settings、Lighting Data Assetとする。

### FR-007 Inspector操作

`StageLightingData` Inspectorは次を提供する。

- アクティブSceneから同期
- ロード済みSceneから一括同期
- DataをアクティブSceneへ適用

Lighting Data AssetをSceneへ適用した場合、Scene保存と再ロードが必要であることを通知する。

### FR-008 Light Probe再構築

`LightProbes.needsRetetrahedralization`を購読する。

同一フレーム内の複数要求をまとめ、`LateUpdate`で`LightProbes.TetrahedralizeAsync()`を一度実行する。

## 4. Scene識別

Scene Pathの完全一致を優先する。

Scene Pathを取得できない場合のみScene NameをFallbackとして使用する。同名Sceneが複数登録されている場合は誤適用を防ぐためFallbackを失敗させる。

## 5. 非機能要件

### NFR-001 実行頻度

登録検索とEnvironment適用はSceneロード時だけ実行する。

毎フレームのScene検索、Asset検索、Object探索を行わない。

`LateUpdate`ではLight Probe再構築要求のboolだけを確認する。

### NFR-002 Editor / Runtime境界

- Runtime AssemblyからPlayerでUnityEditor APIを実行しない。
- Scene Asset、Lighting Data Asset、Lightmapping APIは`UNITY_EDITOR`条件内だけで使用する。
- 自動同期処理はEditor Assemblyへ配置する。

### NFR-003 所有権

- `StageLightingData`: StageとLighting情報の正本。
- Stage Scene: 実際にロードされるベイク済みLighting Dataの所有者。
- `StageLightingExchangeSystem`: Sceneイベント購読と適用順の所有者。
- `StageLightingDataSynchronizer`: Editor自動同期の所有者。

## 6. 非ゴール

- Player実行中のLighting Data Asset直接交換
- `LightmapSettings.lightmaps`の独自再構築
- 時間帯補間
- APV Lighting Scenario切り替え
- Stage Priority
- 現在Stageアンロード後の自動Fallback
- Addressables固有ロード処理
- Scene内Sun、Volume、Reflection ProbeのObject参照管理
- Runtime Debug UI

## 7. 受け入れ条件

1. 未登録Sceneロード時にActive SceneとEnvironmentを変更しない。
2. 登録Stageロード時に対象SceneがActive Sceneになる。
3. 登録StageのEnvironmentが`RenderSettings`へ適用される。
4. Scene保存後にData内のEnvironment、Lighting Settings、Lighting Data Assetが更新される。
5. Lighting Bake完了後にDataが更新される。
6. PlayerコードがUnityEditor APIを参照しない。
7. Additive SceneのLight Probe変更時に非同期再四面体化を要求する。
8. 同名Sceneが複数ある場合にName Fallbackで誤適用しない。

## 8. Revert条件

- Stage SceneをActive化する既存フローと競合する。
- Scene保存時の自動同期が意図しないData Assetを更新する。
- Unity 6000.3でRuntime / Editor Assemblyがコンパイルできない。
- Player BuildへUnityEditor参照が混入する。
- Environment適用後に既存Stageの見た目が変化する。
