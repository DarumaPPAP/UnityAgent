# Migration History

このDirectoryは、UnityAgentの**過去のArchitecture移行・Cutover・Baseline更新・互換削除判断を監査できるように残すHistorical Record**です。

ここに置かれた文書は、現在のProduction Authorityではありません。

現在の正本は次です。

- Policy: `Policy/`
- Context: `Context/`
- Orchestration: `Orchestration/`
- Runtime: `Runtime/`
- Persistence: `Persistence/`
- Operations: `Operations/`
- Eval: `Eval/`

通常のUnityAgent実行、Routing、Context Materialization、Runtime Execution、Policy判断では、このDirectoryをCurrent Stateとして解決しません。

## このDirectoryを残す理由

- 過去にどのAuthorityをどこへ移したか確認する
- Cutover時に何を削除したか確認する
- Historical Replay / Baselineの由来を追跡する
- 現在のContractがどのMigration判断から生まれたか監査する
- 過去の判断をGit履歴だけに依存せず、人間が読みやすい形で保持する

## 命名規約

Migration文書のファイル名は、**開発段階番号ではなく、その文書が表す意味・責務で命名します。**

推奨:

- `canonical-contracts.md`
- `runtime-harness.md`
- `orchestration.md`
- `cutover.md`
- `production-rebaseline.md`
- `baseline-comparator.md`

禁止:

- `phase1-...`
- `phase8-...`
- `phase10-...`
- その他、開発順序番号を文書の恒久的な名前にしたもの

開発順序は時間とともに意味を失いますが、`cutover`、`persistence`、`baseline-comparator` のような責務名は後から見ても内容を判断できます。

`Tools/DocumentationValidator/validate_documentation.py` は、このDirectoryへPhase番号付きファイル名が再導入された場合にFail Closedします。

## Historical literalの扱い

過去に実際に存在したBranch名、Run ID、Artifact名、Baseline IDなどは、監査証跡としてそのまま記録する場合があります。

例:

- 過去のBranch名
- 過去のArtifact ZIP名
- Frozen Baseline ID
- 過去のRun ID

これらは「現在の命名規約としてPhase番号を推奨している」という意味ではありません。実在したHistorical Identifierを改名すると、過去Evidenceとの対応関係が壊れるためです。

## 利用時の注意

新しい実装判断を行う場合は、まず現在のCanonical Sourceを確認してください。

Migration文書は、次の場合だけ補助的に使用します。

1. 過去のArchitecture判断理由を確認したい
2. 削除済みCompatibilityの由来を確認したい
3. Replay / Baseline / Cutoverの監査証跡を確認したい
4. 現在のContractへ至った経緯を追跡したい

Migration文書の内容と現在のCanonical Sourceが競合する場合は、**現在のCanonical Sourceを優先**します。
