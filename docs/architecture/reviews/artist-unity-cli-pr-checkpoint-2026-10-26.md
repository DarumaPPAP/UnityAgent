# Artist Unity CLI統合｜完了記録（履歴）

統合PR: https://github.com/DarumaPPAP/UnityAgent/pull/227

固定検証Revision: `85bcfb4cd41e89efaf63c8345fe36ae7162bda08`。PR最終監査Revision: `4d9f19496f280713df203c75acfd58a2646a1fe0`。

ArtistSubAgent全9コマンドを`unity_cli`へ統合し、旧Artist Provider／独立HostへのProduction依存を撤去した。Unity 6000.3.12f1／6000.6.0f1の7 FixtureとCinematic全10ケースで実Editor PASS、Approval／Scope／Undo／証拠の実観測はPRを参照。固定RevisionのCIは以下で確認できる。

- UnityAgent CI: https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170841
- PR Quality: https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170871
- Windows Bootstrap Smoke: https://github.com/DarumaPPAP/UnityAgent/actions/runs/40269170906

当時の詳細Evidence、Hash、ログ、CaptureはPR #227のGit履歴で確認する。移行完了後の中間Evidenceを現在のTreeと配布資産へ複製し続けない。新しい変更のPASSを過去の実行結果で代用しない。

Windowsの既知Baseline失敗15件（failure4／error11）は残存し、新規Regressionなしという当時の判定。Human Visual Acceptance／Performance／Player／Target Deviceは`not_observed`である。
