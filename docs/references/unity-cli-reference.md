# Unity CLI公式リファレンスの購読・監査基準

UnityAgentのOfficial Unity CLI Providerは、下記のUnity公式資料を定期的に確認し、実装・テスト・Evidence契約の更新要否を判断する。

## 正本資料

- [Unity CLI](https://docs.unity.com/en-us/unity-cli)
- [Unity CLIリファレンス](https://docs.unity.com/en-us/unity-cli/unity-cli-reference)
- [Unity CLIリリースノート](https://docs.unity.com/en-us/unity-cli/release-notes)
- [Unity Pipeline package](https://docs.unity.com/en-us/unity-production-pipeline/local-tools-cli/unity-pipeline-package)

最終確認日: 2026-09-21  
公式資料上の最新CLIリリース: `1.0.0-beta.10`  
実機観測状態: `not_observed`

`1.0.0-beta.10` は公式資料で確認したリリース番号であり、UnityAgentのCIまたは本リポジトリの検証環境で実行したCLIバージョンを意味しない。既存のbeta.3 / beta.8記録は、その時点の実機・Fixture検証結果として保持する。

## 現行Runtimeへの反映

| 公式仕様 | UnityAgentの扱い |
|---|---|
| `unity version --format json` | 構造化versionを優先して読み取り、未対応CLIでは `unity --version` へフォールバックする。 |
| `unity commands --format json` | インストール済みCLIのcommand surfaceを優先して観測し、未対応CLIでは既存のcommand help probeへフォールバックする。 |
| `unity test` 終了コード `6` | テスト結果が未完了・未観測のため、`execution_failed` として扱う。 |
| `unity test` 終了コード `7` | Unity service unavailableとして `unavailable` に分類する。再試行可能性は上位の実行Policyで判断する。 |
| `unity test` 終了コード `8` | テスト自体の失敗を示すため、XMLがなくても `observed_test_failure` として扱う。 |

CLIは実験的仕様であり、実際にインストールされたCLIの `unity --help` が最終的なcommand/option authorityである。Providerは、公式資料に存在するコマンドを固定的に利用可能とみなさず、Environment discoveryの観測結果と既存の安全なallowlistを優先する。

## 更新手順

1. リリースノートで追加・変更・削除されたcommand、option、終了コード、セキュリティ修正を確認する。
2. 現行Providerのbuilder、discovery、result mapper、Provider capability gateを照合する。
3. 仕様変更ごとに、旧CLI fallbackと新CLIのmachine-readable outputを含む回帰テストを先に追加する。
4. Unity CLIやPipelineを実際に実行していない場合は、Evidenceを `not_observed` のままにする。
5. UnityAgentのControl Plane境界、No auto-install、Fail-Closed、Approval、Evidence契約を緩和しない。
