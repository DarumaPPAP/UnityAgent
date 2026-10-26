# Artist Unity CLI統合の最終検証記録

## 判定とRevision

ArtistSubAgent全9コマンドの `unity_cli` 統合と、旧Artist Provider／独立HostのProduction依存撤去を完了した。固定Matrix、Cinematic全10ケース、実Mutation、安全性、Development配布物の必須Editor GateはPASS。Windows上の全Runtime・layout・architecture検証には開始Commitでも再現する既存失敗があり、全検証成功とは扱わない。新規Regressionは観測されなかった。

実行・配布物の固定Revisionは `85bcfb4cd41e89efaf63c8345fe36ae7162bda08`、最後のProductionコード変更は `98208457f263966d4a94931c3024c969d34a3d24`。両者の `src/unityagent` とArtist Editor正本の差分は空。後続の監査Commitは本記録とEvidenceのみを追加し、検証入力を変更しない。最終PR本文に監査Commit SHAとそのCIを記載し、固定Revisionからの差分と[ソースHash](../../../tests/unity/evidence/artist/unity-cli-completion-2026-10-26/verified-source-hashes.json)を再照合する。

[Evidence索引](../../../tests/unity/evidence/artist/unity-cli-completion-2026-10-26/index.json)に各結果、入力Hash、XML、CI、Baseline比較を収録した。[永続Evidence ZIP](../../../tests/unity/evidence/artist/unity-cli-completion-2026-10-26/durable-evidence.zip)は155レコードの整合性、イベント、Provider結果、Context manifest、Capture画像を再検証して格納した。Approval Store・Authority秘密情報は含めない。過去の検証記録や旧PRのPASSは今回の根拠に使用していない。

## 根本修正

- 対象Project Catalogが実行可能なのに、無関係な全Projectの `unity pipeline list` がtimeoutしてArtist unavailableになる経路を撤去。Project限定のCatalog観測を正本とし、失敗を分類した。Mutationの自動再試行は追加していない。
- CLI 1.0.0-beta14の `unity status` がPipeline 0.8へ未定義の `editor status` を送り、Editor Errorを発生させる不整合を実測。Catalogに観測した `editor_status` をProject限定で実行し、結果・両Project root・Version・compile/reload状態を検証する。
- Project root未取得とscope違反を区別。Artistの `partial` 応答は内容を保持しつつ、StateStoreへは有効な `blocked` 状態で永続化する。
- 有効なUPM `file:` tgzを未インストールと誤認する不具合を修正。展開せず、64KB以内の通常 `package/package.json` のみ読み、既存name/version照合を維持する。
- Routing SkillのOutput Contract／Checklist／Common Mistakesを実質的な内容で補い、正本・Mirror・P9 manifestを同期した。

## Unity実Editor検証

PlatformはWindows 11、Python 3.12.10、Unity CLI 1.0.0-beta14。GPUはAMD Radeon RX 5700 XT／Direct3D12。ユーザーの本番Projectを使わず、専用Fixtureを生成した。6000.6.0f1は固定検証対象でありLTSという意味ではない。`tests/unity/matrix.yaml` は変更していない。

| Fixture | Editor | 成功テスト数 | 結果 |
|---|---|---:|---|
| minimal-6000.3 | 6000.3.12f1 | 1 | PASS |
| minimal-6000.6 | 6000.6.0f1 | 1 | PASS |
| canonical-full | 6000.6.0f1 | 35 | PASS |
| p9-lts-urp | 6000.3.12f1 | 1 | PASS |
| builtin-smoke | 6000.6.0f1 | 3 | PASS |
| urp-smoke | 6000.6.0f1 | 3 | PASS |
| hdrp-smoke | 6000.6.0f1 | 3 | PASS |

全9コマンドは6000.3.12f1 Built-in／URP、6000.6.0f1 Built-in／URP／HDRPでPASS。Control Plane → Broker → Unity CLI → Pipeline → Editor → Persistence、旧Host不在、単回使用、入力Hash一致を確認した。LTS Built-inと6000.6 URPは隔離wheelと実UPM tgzを使用。URP ColorAdjustmentsは両Editor、HDRP Fogは6000.6で実Mutation・実状態・保存禁止・入力Hashを確認した。

| Cinematicケース | 結果 | 確認範囲 |
|---|---|---|
| activation | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| binding | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| animation | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| control | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| signal | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| marker | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| cinemachine_shot | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| cinemachine_shot-update | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| shot | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |
| shot-update | PASS | Plan / Preview / Approval / Apply / Inspect・実状態・Replay拒否・永続Evidence |

Cinematicは6000.6の固定Revision実行を主根拠とし、LTSでも同一ProductionソースHashの全10ケースがPASS。保存前後のScene／TimelineファイルHashも一致した。

## Approval・Scope・Undo・失敗Evidence

実Control Plane拒否テスト10ケースはcaller context、偽造token、別Project、別Run、scope拡大、過去期限での発行、期限切れ、取消、stale revision、成功後Replayを確認した。Exact Diff／直接Pipeline迂回拒否はEditor Authorityテストを含む35件で確認した。stale revisionは認可前に拒否するため、消費済みを偽装しない。

`UNITY_ARTIST_TEST_FAULTS` の所有Fixtureに対する2ケースは、実適用後の例外とUndo成功、所有LightのUndo履歴を明示的に消した場合のUndo不能を確認した。両方blocked・verified false・成功Evidence不在・再利用拒否。通常assemblyは注入hookを含まず、通常LTS35件も再実行してPASS。

Apply後の応答喪失は、実Editorの成功応答を観測した後、Runtime transport境界で応答を失わせる注入試験。Camera FOV 47→48を独立Inspectで確認し、Mutation dispatchは1回、host結果blocked、失敗Evidence永続化、承認execution_started維持、Replay拒否、Scene未保存を確認した。物理的なネットワーク切断試験とは区別する。

## 旧Provider／Host監査

Runtime Registry／Resolver、Installer／Setup、CI／Release、配布物に旧Hostの新規実行・build・install・fallback依存はない。全9コマンドの現行Backendは `unity_cli`。旧Hostソースは不要で、旧Host不在E2Eは全環境でPASS。

`unity_artist_cli` の残存はSnapshot／Receiptの履歴読取互換と明示的拒否。`UnityArtistCLI` は既存Editor応答のproduct識別子に残るが、独立Hostを起動する意味ではない。必要な互換・拒否テスト・歴史記録を削除していない。

## Development配布物

すべて `85bcfb4cd41e89efaf63c8345fe36ae7162bda08` から生成した。Artist UPM37ファイル、UnityAgent UPM223ファイル、wheel同梱resource266ファイルを正本とbyte単位で照合し、wheel隔離インストール・実Package解決・Lock・隔離環境E2Eを確認した。[配布物Hash](../../../tests/unity/evidence/artist/unity-cli-completion-2026-10-26/development/revision-hashes.json)とPackage manifest／lockを保存した。

| 配布物 | SHA-256 |
|---|---|
| com.darumappap.artist-subagent-0.0.2-beta.tgz | `ef38b47b046d025035a0769eb8318eb056638252d7deaf82a7226d4c41eea935` |
| com.darumappap.unity-agent-0.0.8-beta.tgz | `d3b0568518791be3019a82da247cf032323edbffea212e2a24bcaa497724650c` |
| unityagent_control_plane-0.0.8b0-py3-none-any.whl | `594925b53e0fb5cbe86c80ed10372de76ebd6b9cb9ee8a87e29a63bd43861dbc` |

配布物はDevelopment検証用。Release／Tagは作成していない。Rollbackは配布前のCommit／Package参照へ戻す運用とし、旧HostをFallbackとして復活させない。

## Python回帰・CI・既存失敗

- Artist関連Runtime106件：105成功・symlink環境制約1skip。Packaging33件、Context Explorer18件は全成功。
- Windows `validate_all.py` 内Runtime726件：failure4／error11／skip6。開始Commit010318ceの独立checkout・同一Python／TEMP／resource生成条件で722件中同じ15問題を再現し、current-onlyは0。[比較](../../../tests/unity/evidence/artist/unity-cli-completion-2026-10-26/verification/baseline-comparison.json)に各テスト名を保存した。
- Windows layoutのEval／Tools／Tests大小文字alias、およびarchitectureのsymlink権限エラー3件もBaselineで再現。Gateを緩和せず失敗ログを残した。
- 固定RevisionのGitHub Actionsは[UnityAgent CI](https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170841)、[PR Quality](https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170871)、[Windows Bootstrap Smoke](https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170906)がすべてPASS。後続監査CommitのCIはPR本文で追跡する。
- 独立コードレビューのCritical／Important所見は0件。

## 制限と運用

Human Visual Acceptance、Performance、Player、Target Deviceは `not_observed`。実GPU readbackは見た目の人間承認や実機性能の証明ではない。物理的通信切断、実機Build、性能値をPASSに変換していない。

作業Branchは `feature/artist-unity-cli-completion`、PRはDraft維持。Merge、Release、Tag、Repository Archive、破壊的履歴変更は行わない。Windows既存失敗は残存事項として管理し、今回の移行必須Editor Gateと分離する。
