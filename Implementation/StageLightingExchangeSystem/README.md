# Stage Lighting Exchange System

Unity 6000.3向けのStage Scene Lighting切り替え実装です。

## 配置

`Implementation/StageLightingExchangeSystem/Runtime`と`Editor`をUnityプロジェクトの任意の`Assets`配下へコピーします。

## セットアップ

1. `Create > Stage Lighting > Stage Lighting Data`から`StageLightingData`を作成する。
2. EntriesへStage Sceneを登録する。
3. 各Stage Sceneを開き、LightingをBakeしてSceneを保存する。
4. Scene保存またはBake完了時に、Environment、Lighting Settings、Lighting Data AssetがDataへ同期されることを確認する。
5. Bootstrap SceneのGameObjectへ`StageLightingExchangeSystem`を追加し、作成したDataを設定する。
6. Stage SceneをAdditive Loadする。

登録済みSceneがロードされると、そのSceneをActive Sceneへ変更し、保存済みEnvironmentを適用します。未登録Sceneは処理しません。

## Lighting Data Assetの扱い

Lighting Data AssetはPlayer実行中に直接交換しません。

EditorでDataとSceneの割り当てを同期し、PlayerではStage Sceneロード時にUnityが読み込んだLighting Dataを使用します。Inspectorの`DataをアクティブSceneへ適用`で割り当てを変更した場合は、Sceneを保存して開き直してください。

## Light Probe

Additive SceneのロードまたはアンロードでLight Probe数が変化した場合、`LightProbes.needsRetetrahedralization`通知を受け、同一フレーム内の要求をまとめて`LightProbes.TetrahedralizeAsync()`を実行します。

## 制約

- Scene識別はScene Pathを優先する。
- Pathを取得できない場合のみScene Nameを使用する。
- 同名Sceneが複数登録されている場合、NameによるFallbackは適用しない。
- Active Scene変更により、以後生成されるGameObjectの所属先も変更される。
- 時間帯補間、APV Lighting Scenario、複数StageのPriority制御は対象外。
