# UnityAgent 起動・接続・取得 Smoke（新正本）

目的は **UnityAgentが起動し、対象Unity Projectを識別し、接続用Capabilityを解決し、取得したFactとEvidenceを誤報しない** こと。現行実装で利用できるPython標準 `unittest` と既存Runtime APIを直接使い、独自Test Framework／新Fixture DBは作らない。

```bash
python tools/validate_all.py --profile smoke
# または直接
python -m unittest discover -s tests/smoke -p 'test_*.py' -q -b
```

| Source | Purpose | Reuse / why existing Test is not simply retained | Boundary | Retirement |
|---|---|---|---|---|
| `test_bootstrap.py`（8ケース） | 公開CLIの起動口・Project解決・Unity Versionの観測 | 既存CLIとproject_identityを使用。従来の12件超のProject CLI各コマンド検証は接続Smokeには過剰で、必要な公開契約のみ再評価 | Unity Editor起動を含まないPython入口 | 実CLIの同等な契約Smokeに完全移譲できれば統合 |
| `test_connection.py`（11ケース） | Registry、Doctor、Unity CLIコマンド生成、構造化結果・未観測拒否 | RuntimeProviderRegistry、Unity CLI Command Builder、Result Mapperを直接使用。旧大型Provider FixtureへのTestCase依存を作らない | 接続境界。Mock Successを実Editor E2Eに読み替えない | 実接続Evidenceが自動で再現可能かつ同等拒否系を守れれば統合 |
| `test_read.py`（8ケース） | 実File read、Project設定取得、Policy/Project境界、秘匿Evidence | FileProviderと既存observation_payloadを使用。ファイルシステムをPython一時領域で構築するため外部Fixtureは不要 | Readだけ。Mutation/Approvalの正当性をこのSuiteで主張しない | 実Editor / Target DeviceのRead Smokeが同じFailureを検出できる場合に再評価 |

Pythonの観測レベルは **static / host-Python / real-Editor** を明確に分ける。上記27件はHostのAPI境界を確認するが、Unity本体への実接続やコンパイルのPASSではない。既存Unity 6.3 Editor Fixture・実Production Smokeが実行可能な環境で成功したときだけreal-EditorのEvidenceとみなす。

### 段階的移行と安全性

- `tools/validate_all.py --profile smoke` は27件だけを実行するFast Path。旧スイートを消したこと・全製品機能を保証したことにはならない。
- `tools/validate_all.py --profile full` または従来の引数なし実行は **旧14 Suite + 32 Validator** を維持。PR CIの必須Safety Regressionは本変更では削除しない。
- `tests/delete/` は旧Testの原本退避だけに使用。新Smokeの検出能力の同等性が未確認な旧Testは凍結・削除しない。
- 次の削減は旧Testの保護するInvariantのうち、`startup / connection / read`に関係しないものを「製品保証対象外」にするか別Gateへ維持するかで判断する。Approval/Scope/Mutation/Evidenceの危険な拒否条件は、正式なRisk Decisionと回帰移管まで残す。
- 実Unity Editor、PlayMode、Player、Target Deviceは未実行をPASSにせず、環境がない場合は `BLOCKED_NOT_RUN` と記録する。
