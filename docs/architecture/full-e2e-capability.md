# UnityAgent Full E2E Capability

Codex Plugin相当のホストCLIから UnityAgent Control Plane、Tool Broker、Unity Editor、Editor PlayModeへ進む固定の検証フロー。対象Projectに `Assets/UnityAgentE2E` を作り、Scene、CubeのGameObject、Material、`FullE2EProbe.cs` を生成する。生成内容は事前のPlanに固定され、任意のScriptやEditorコマンドを受け取らない。

## 前提

- Unity Projectを対応するバージョンのUnity Editorで開き、この変更を含む `com.darumappap.unity-agent` Packageを導入する。
- 同じ変更を含むUnityAgentホストCLIを使用する。PackageとCLIでScript Templateが異なるとEditorが拒否する。
- 開いているSceneは保存済みで、EditorはCompile中・PlayMode中ではない。`Assets/UnityAgentE2E` とその `.meta` は存在していない。
- `--state-root` はProjectの外側に置く。省略時はホストのUnityAgent状態ディレクトリを使用する。

## 実行

```bash
python Tools/unity_agent_cli.py e2e plan --project-path /path/to/UnityProject --state-root /path/to/UnityAgentState
python Tools/unity_agent_cli.py e2e approve --project-path /path/to/UnityProject --state-root /path/to/UnityAgentState --plan-id PLAN_ID
python Tools/unity_agent_cli.py e2e approve-save --project-path /path/to/UnityProject --state-root /path/to/UnityAgentState --plan-id PLAN_ID
python Tools/unity_agent_cli.py e2e apply --project-path /path/to/UnityProject --state-root /path/to/UnityAgentState --plan-id PLAN_ID --approval-ref APPROVAL_REF --save-approval-ref SAVE_APPROVAL_REF
```

`plan` はUnity Projectを変更せず、作成予定のScene / Material / Script / `.meta` の `exact_diff`、Cubeの `scene_object_diff`、Material shaderの選択候補、生成Script全文 `script_preview` とSHA-256、未作成の対象状態、承認が必要なUndo手順を表示する。ShaderはEditor環境で候補の先頭から選び、実際の選択結果を署名付きResultに残す。内容を確認してから `approve` と `approve-save` を別々に実行する。各承認はPlan、Project、対象Path、期限に結び付く。`apply` は期限切れ、承認の取消、既存対象Asset、別Projectなどを拒否する。Editorの準備後にPlanが古くなった場合は新しく作成する。

## 実行経路と検証

1. Control PlaneがPolicy、Approval、Project binding、Mutation Scopeを確認し、`scene.mutate` と `workflow=full_e2e` をTool Brokerへ渡す。
2. Brokerが固定の `unity_agent_editor` Providerを解決する。Providerは新鮮なEditor heartbeatと署名付きジョブで同一ProjectのEditorへ要求を渡す。
3. EditorがAssetDatabase / EditorSceneManager APIでAssetとSceneを作成する。Scene YAMLの直接編集はしない。Scriptをimportして `MonoScript.GetClass()` と `EditorUtility.scriptCompilationFailed` を確認し、SceneにComponentを追加して保存する。
4. EditorがPlayModeへ入り、Cube上のScriptの `Start()` 実行を `WasStarted` で観測する。PlayMode終了後、結果を署名して返す。
5. Providerが署名、Plan、Editor instance、承認、実在する作成Asset、Script hash、Exact Diffを検証する。Control Planeが正規Evidenceを記録した場合だけ `completed` を返す。

保存場所は `STATE_ROOT/full_e2e/plans/PLAN_ID.json`、`STATE_ROOT/full_e2e/runs/RUN_ID/result.json`、署名済みEditor結果を受け取れた場合は同じRunディレクトリの `editor-result.json`。`result.json` は正規 `evidence_refs` と `control_plane_state_ref` を持つ。Editor不在やCompile / PlayMode失敗でも `result.json` に `blocked` と観測状態を保存する。途中まで作成したAssetは自動削除せず、署名済み結果から作成済み状態を記録する。再実行には別途承認した上でUnity EditorのProjectウィンドウから対象を削除し、作成専用Planを再生成する。

Heartbeat、署名と結果ファイルは同一OSユーザーのローカルWorkspaceを信頼する。別プロセスの同一ユーザーがProjectの `Library` や状態ディレクトリを書き換えられる状況ではEditor由来を暗号学的に証明できない。Hostは実行中のUnityプロセスのPIDと実行ファイルを照合するが、Host自身とWorkspaceへの敵対的アクセスを想定したAttestationではない。`exact_diff` の実測範囲は新規Probeディレクトリであり、Project全体の他の変更を網羅する監査ではない。

この検証のPlayModeはUnity Editor内の実行であり、Player buildや実機での動作確認は含まない。Editorのない環境では `compile` / `playmode` を成功扱いしない。
