# StageLightingExchangeSystem Tasks

- FeatureName: `StageLightingExchangeSystem`
- Status: Implemented
- LastUpdated: 2026-07-24

## STLG-001 StageLightingData実装

- Status: DONE
- Goal: Stage Scene、Environment、Lighting Settings、Lighting Data Assetを保持する。
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Runtime/StageLightingData.cs`
- Done:
  - Scene Path優先検索
  - 同名SceneのFallback拒否
  - Environment Capture / Apply
  - Editor用Lighting参照保持

## STLG-002 Runtime交換処理実装

- Status: DONE
- DependsOn: STLG-001
- Goal: 登録StageのSceneロード時だけLightingを有効化する。
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Runtime/StageLightingExchangeSystem.cs`
- Done:
  - Sceneロード購読
  - 未登録Sceneスキップ
  - Active Scene切り替え
  - Environment適用
  - DynamicGI更新
  - 起動時ロード済みScene確認

## STLG-003 Light Probe再構築実装

- Status: DONE
- DependsOn: STLG-002
- Goal: Additive Scene変更後のLight Probe四面体構造を更新する。
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Runtime/StageLightingExchangeSystem.cs`
- Done:
  - `needsRetetrahedralization`購読
  - 同一フレーム内の要求集約
  - `TetrahedralizeAsync`実行

## STLG-004 Editor自動同期実装

- Status: DONE
- DependsOn: STLG-001
- Goal: SceneとDataのLighting情報を自動同期する。
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Editor/StageLightingDataSynchronizer.cs`
- Done:
  - Scene保存後同期
  - Lighting Data更新後同期
  - Bake完了後同期
  - Active Scene一時変更と復元
  - 変更DataのみDirty化

## STLG-005 Inspector操作実装

- Status: DONE
- DependsOn: STLG-004
- Goal: 同期と逆適用をInspectorから実行できるようにする。
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Editor/StageLightingDataEditor.cs`
- Done:
  - アクティブScene同期
  - ロード済みScene一括同期
  - DataからSceneへの適用
  - Scene再ロード要件の通知

## STLG-006 Assembly境界と導入資料

- Status: DONE
- DependsOn: STLG-001, STLG-002, STLG-004
- Changed files:
  - `Implementation/StageLightingExchangeSystem/Runtime/StageLighting.asmdef`
  - `Implementation/StageLightingExchangeSystem/Runtime/AssemblyInfo.cs`
  - `Implementation/StageLightingExchangeSystem/Editor/StageLighting.Editor.asmdef`
  - `Implementation/StageLightingExchangeSystem/README.md`
- Done:
  - Runtime / Editor Assembly分離
  - Editor Assemblyへのinternal公開
  - セットアップと制約を記録

## 未実施の検証

- Unity 6000.3でのコンパイル
- Editor上のScene保存・Bakeイベント確認
- Player / IL2CPP Build
- Nintendo Switch実機確認
