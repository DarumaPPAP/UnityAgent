# Unity Editor検証Fixture

現行の実行対象とサポートVersionは [tests/unity/matrix.yaml](../matrix.yaml) を正本とします。

過去の移行時Evidenceは [Artist Unity CLI統合PR #227](https://github.com/DarumaPPAP/UnityAgent/pull/227) の履歴にあり、現在のEditor検証成功の代わりにはなりません。

Editor・Pipeline・Capture・Visualの結果は、実行ごとの証跡で個別に判定します。未観測は `not_observed`、前提不足は `BLOCKED_NOT_RUN` として扱います。
