# 非公開CIの承認・永続状態・段階的再開

## 現在の対応範囲

UnityAgent側には、承認の検証、段階ごとの状態保存、チェックポイント照合、再開時の拒否条件を実装している。非公開リポジトリで動かすワークフローのひな形は `ci/private/production-e2e.yml` に配置した。

**非公開リポジトリへの配置、ライセンス付きUnity Editorでの実行、Blender MCPとの実接続は未実施（`BLOCKED_NOT_RUN`）。** ホスト側の契約テストが成功しても、実環境での一連の動作が成功したことにはならない。

## 責務と保管場所

| 対象 | 責務・制約 |
|---|---|
| 公開側のUnityAgent | Control Plane、承認照合、実行制限、永続化、テストの正本 |
| 非公開の実行リポジトリ | 承認用のプルリクエスト、保護されたワークフロー、専用のWindows実行環境 |
| `UNITYAGENT_STATE_ROOT` | 実行環境のアクセス制限された永続領域。Unityプロジェクトの**外側**に置く |
| GitHub Actionsの成果物 | 監査・複製用。再開時に参照する正本状態として採用しない |
| `UNITYAGENT_APPROVED_SHA` | レビュー済みソースの固定Commit SHA。開発版のRevision整合に使用し、Releaseとは区別する |

実行状態、Blenderの作業記録とFBX、承認判断、証拠、チェックポイントは、既存のUnityAgent永続化層で扱う。UnityのAsset、ライセンス情報、アクセストークンを公開側やActionsの成果物に含めない。

実行権限の最終判断はUnityAgentのControl Planeが持つ。ワークフロー入力の文字列を承認と見なさない。独立した実行制御層は増設せず、段階実行用の処理も既存のBroker経由で呼び出す。

## 非公開の実行環境を用意する

1. 非公開の実行リポジトリに、グラフィックス処理とUnity `6000.3.12f1` のライセンスを利用できる専用Windows Runnerを接続する。ラベルは `self-hosted`、`Windows`、`unity-6000.3.12f1`、`private-only` とし、公開プルリクエストのジョブとは共有しない。Runnerグループ、既定ブランチ、承認ファイル、実行用Environmentを保護する。
2. `ci/private/production-e2e.yml` を非公開リポジトリの `.github/workflows/production-e2e.yml` に配置する。
3. 保護された変数に `UNITYAGENT_STATE_ROOT`、`UNITYAGENT_APPROVED_SHA`、`UNITYAGENT_PRIVATE_APPROVERS`（承認可能なGitHubユーザー名）、`UNITYAGENT_PRIVATE_STAGE_DRIVER`（事前に監査して導入した段階実行スクリプトの絶対パス）を設定する。
4. `GITHUB_TOKEN`には非公開リポジトリ内のレビュー・ファイル・共同作業者権限の**読み取り権限**が必要。取得失敗や権限不足では承認を拒否する。トークンを永続状態やログに記録しない。
5. 信頼できる実行環境で既存のBlender作業記録と `rock-import plan` を作成する。その後、レビュー済みソースから**一度だけ**実行を登録する。

```powershell
$env:PYTHONPATH = "C:\reviewed\UnityAgent\src"
python -m unityagent.control_plane.private_production_ci register `
    --state-root "D:\UnityAgentState" --run-id "rock-rock-g1" `
    --plan-id "<保存済みの計画ID>" `
    --source-revision "<レビュー済みの40文字Commit_SHA>"
```

`run_id` は `rock-` とBlenderの `job_id` を連結した値に固定する。計画、FBXのハッシュ、プロジェクトRevision、ソースSHAが一致しなければ登録できない。同じ実行を再登録して状態を初期化することも拒否する。

## 操作ごとの承認

非公開リポジトリ内で、次の配置に承認内容を記載したプルリクエストを作る。

`approvals/<run_id>/<stage>/<kind>.json`

必要な承認種別は、成果物の確認で `stage`、Unityへの適用で `mutation` と `save` の**別承認**、目視確認で `stage`、復旧で `rollback` とする。

記録例は次のとおり。山括弧で示した値は例示であり、実行時には保存済みの計画・現在の進捗から正確な値を転記する。

```json
{
  "schema_version": "1.0",
  "run_id": "rock-rock-g1",
  "requested_stage": "editor",
  "kind": "mutation",
  "plan_id": "<保存済みの計画ID>",
  "plan_digest": "sha256:<計画のハッシュ>",
  "source_revision": "<固定済みのCommit_SHA>",
  "artifact_sha256": "<FBXのSHA256>",
  "project_revision": "sha256:<直前段階のプロジェクトハッシュ>",
  "scope_paths": ["<計画で許可した正確なパス>"],
  "expires_at": "<タイムゾーン付き有効期限>"
}
```

承認者は明示された許可リストに含まれ、対象リポジトリに書き込み以上の権限を持つ必要がある。申請者本人の承認では通過しない。GitHub APIから**最新のプルリクエスト先頭Commitに対するレビュー**と、そのCommitに含まれる承認ファイルを取得し直す。

承認の取り消し、対象Commitの変更、変更要求、期限切れ、計画・対象範囲・Revisionの不一致、APIの失敗はすべて拒否する。適用と保存は別々の承認が必要で、Editorへ渡す直前にも確認し直す。既存の `rock-import approve` コマンドだけでは、非公開CIの承認を代替できない（`UNITYAGENT_REQUIRE_PRIVATE_APPROVAL=1`）。

## 段階実行と再開

ワークフローには既存の `run_id`、次の `stage`、承認用プルリクエスト番号の対応を示す `approval_pulls` だけを渡す。例えば `{"mutation":42,"save":43}` のような対応を用いる。数値は例であり、ドキュメントの識別番号や固定の運用番号ではない。

段階の実行順序は以下に固定する。

`artifact → editor → visual → rollback`

| 状態 | 確認条件 | 結果 |
|---|---|---|
| `waiting` | 次の段階であること、承認・計画・Revision・過去のチェックポイントが有効 | `running` に移行し、GitHub実行IDと承認参照を保存 |
| `running` | 必須の観測ファイルとハッシュが揃い、承認を再検証できる | 不変の受領記録とチェックポイントを作成し、次段階へ進む |
| `running` の中断・時間切れ・結果不明 | 外部副作用が確定していない | `RECONCILIATION_REQUIRED` として停止。**自動再送しない** |
| すべての状態 | プロジェクト・計画・ソースの変更、証拠欠落、承認無効、チェックポイント破損 | 拒否。既存状態を黙って書き換えない |
| 全4段階の終了 | 必須の観測資料を収集 | `host_gate_contracts_complete=true`。独立した実環境監査までは `production_verified=false` |

段階ごとにGitHub Actionsの実行IDは変わるが、UnityAgent内の `run_id` は維持する。

`CheckpointStore` が復元するのは**状態のみ**。Unity Assetの復旧には、別の承認を受けたEditor操作でハッシュ・GUID・所有範囲を照合する必要がある。チェックポイントの復元や `git reset --hard` をAssetの復旧手段として使用しない。

段階実行スクリプトは、`<StateRoot>/evidence/<run_id>` に各検証項目のJSONと、ハッシュ付きの生データを記録する。接続用コードは**観測データを捏造しない**。記録元の真正性の確認は、信頼された実行環境と独立監査が必要。

### G1で必須とする検証

`production_runtime`、`blender_mcp`、`artifact_integrity`、`unity_compile`、`import_prefab_scene_guid`、`render_capture`、`visual_acceptance`、`rollback`、`lease_conflict` の9項目。

`video_decode`、`hot_reload_comparison`、`g2`、`g3` は別々に報告し、G1の完了条件には含めない。

## 契約テストと未検証事項

```sh
PYTHONPATH=src python -m unittest tests.runtime.test_private_production_ci tests.runtime.test_production_e2e_evidence -v
```

このテストで確認するのは、承認・期限・取消・対象範囲・実行の同一性・再開拒否・証拠照合などの**ホスト側の契約**に限る。

非公開リポジトリの作成・配置、Runnerのアクセス権確認、段階実行スクリプトの実接続、Unity Editor、Blender MCP、目視確認と実Rollbackは `BLOCKED_NOT_RUN` のままである。ひな形が配置されただけで、本番運用に使えるとは判定しない。
