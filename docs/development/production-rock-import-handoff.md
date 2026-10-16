# Blender制作物をUnityへ取り込む実行契約

承認済みの全体方針は [Production E2Eの決定事項](../decisions/production-e2e/approved-goal.md) を参照する。この文書は、既存のControl Planeから固定された岩モデルを取り込むための操作と安全条件を説明する。開発上の変更履歴やプルリクエスト番号を、実行仕様の識別子としては使わない。

## 適用範囲

Blender MCPの出力は**一時保管された制作物**であり、それ自体はUnityでの一連の検証結果ではない。Unity Editorへの変更処理 `scene.mutate` は、UnityAgentのControl Planeと既存の `native_rock_import` を経由する。

ホスト上の契約検証、Unity Editorでの実動作、目視確認、復旧の成功は区別する。実行していない必須項目は `BLOCKED_NOT_RUN` のままとする。

## Blender MCPとの互換性と安全条件

- 上流の `get_scene_info` が返すのは整形済みの文字列であり、`structuredContent.blender_session_identity` は含まれない。
- 承認済みの固定セッション検証でアドオンと通信手順の状態を確認し、Blenderの `WindowManager` に協調的な識別値を設定する。ホスト側のセッション排他を保持した状態で再確認する。
- この識別値はOSによるプロセス認証や隔離を保証しない。UnityAgentの排他を守らない別のSocketクライアントを防げないため、専用のBlender環境を使用する。
- MCPサーバーへ `BLENDER_MCP_SAFE_MODE=1` を渡す。固定の制作スクリプトが使用するのは、許可済みのBlender API、`math`、`json`、`mathutils` に限定する。出力FBXのハッシュはホストが計算し、`artifact.json` に記録する。
- Safe Modeは構文木の検査であり、ファイルシステムやネットワークを隔離する仕組みではない。
- アドオン状態が不明、セッション変更、出力不整合、作業記録の信頼性不足、結果不明の時間切れの場合は**再送せず停止**する。

## 取り込み手順

最初に、完了済みの `rock apply` の作業記録と、一時保管されたFBXを取得する。

```sh
unity-agent rock-import plan --project-path PROJECT --state-root OUTSIDE_PROJECT --job-id rock-g1
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind mutation
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind save
unity-agent rock-import apply --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --approval-ref MUTATION_REF --save-approval-ref SAVE_REF
```

`plan` の作成には、完了済み作業記録との一致、FBXのSHA-256、空の `Assets/UnityAgentRockG1`、プロジェクトRevision、固定された定義が必要となる。取り込みと保存には、それぞれ別の期限付き承認を要求する。

`workflow=blender_rock_import` が指定された `scene.mutate` を、既存のToolBrokerが `native_rock_import` に解決する。RuntimeはプロジェクトのEditor排他を取得し、許可済み範囲に `Rock.fbx` と既存の `.meta` の変更前情報を保管する。

Unity Editorで呼び出せるのは、事前に許可した**2つの固定メソッド**のみ。任意の `executeMethod` は受け付けない。Editor側も承認を再確認し、モデルの取り込み設定・マテリアル・Prefab・Sceneのファイル単位の受領記録を保存する。

`production_import=completed` は `verified=true` を意味しない。画面の目視確認、Player、G2、G3などは別の検証項目として維持する。

## 別承認による復旧

```sh
unity-agent rock-import approve --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --kind rollback
unity-agent rock-import rollback --project-path PROJECT --state-root OUTSIDE_PROJECT --plan-id PLAN_ID --rollback-approval-ref ROLLBACK_REF
```

Editorは取り込み時の受領記録のハッシュ、所有ファイルすべてのハッシュとGUID、所有範囲外のファイルが存在しないことを検証する。その後に限り、固定ディレクトリに対して `AssetDatabase.DeleteAsset` を呼び出す。

他者による変更やEditorの失敗が見つかった場合は停止して、外部副作用を照合する。`git reset --hard` やScene・Prefab・Materialの生YAMLを直接変更する方法には切り替えない。

## 実環境で確認が必要な事項

Unity `6000.3.12f1` のライセンス、URP、グラフィックス処理に対応したWindows実行環境を接続するまでは、以下は `BLOCKED_NOT_RUN` とする。

- 実際のBlender MCPサーバーとアドオンのバージョン確認、Safe Mode、セッション識別値の再照合。
- `RockImportBridge.cs` のUnity Editorでのコンパイル。
- BlenderからFBXを生成し、Broker経由でEditorへ取り込み、マテリアル・Prefab・Scene・受領記録まで生成する一連の実行。
- QAの証拠、画面の目視確認、取り込み失敗からの復旧、限定Rollback、同時手動編集との競合。

ホストテストと通常CIで検証できるのは、入出力契約、有限の実行要求、承認、対象範囲の拒否、制作物のハッシュ、配布ソース整合性などに限られる。実機で観測した証拠には置き換えられない。

## 運用上の制約

BlenderアドオンのSocketへ別プロセスから接続できる場合、協調的なセッション識別値と排他制御だけでは操作を防止できない。信頼できない処理を実行する前に、OS側の作業領域・プロセス隔離を別途確保する。

C#側の取り込み先は固定の検証用ディレクトリである。任意パスへの汎用化や、QAの推論結果から直接変更を実行する仕組みまで実装済みとみなさない。
