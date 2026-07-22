# UnityJapaneseConsoleWindow v0.3.0 Tasks

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.3.0`
- Status: Proposed
- Plan: `Specs/UnityJapaneseConsoleWindow/plan.md`
- TargetRoot: `Assets/__MyRepository/JapaneseConsoleWindow`
- RootNamespace: `DarumaPPAP`

## 実行規則

- 全Taskの初期状態は`PENDING`とする。
- 依存Taskが`COMPLETED`である未完了Taskを原則1件ずつ実装する。
- Task内でコンパイル成立に不可欠な関連ファイルだけは、明記範囲内で同時変更できる。
- 完了条件をすべて満たした場合だけTaskを`COMPLETED`へ更新する。
- Unity Editor手動確認が必要なTaskは、静的実装とEditMode Testだけで完了扱いにしない。
- 自動テスト、Importer、製品コードからWebへ接続しない。
- Google Cloud、DeepL、Azure、OpenAI、LibreTranslate、API Key、外部Endpointを追加しない。
- Source Licenseが未確認のRule群をRepositoryへCommitしない。
- Candidate Ruleを自動でApprovedへ変更しない。
- 停止条件に該当した場合は、Blocker、影響FR/NFR/AC、推奨仕様変更、製品コード変更有無を報告する。

---

## UJCW-030-001 Observation集約・Allocation修正

- Status: `PENDING`
- 目的: 同一ログのOccurrenceごとにObservationが増殖・複製される問題を解消する。
- 変更予定ファイル:
  - 変更: `Editor/Aggregation/LogAggregationStore.cs`
  - 変更: `Editor/Model/LogRecord.cs`
  - 変更: `Editor/Tests/EditMode/LogAggregationStoreTests.cs`
  - 変更: `Editor/Tests/EditMode/LogModelTests.cs`
- 依存Task: なし
- 対応要件: FR-043、FR-044、NFR-005、AC-016
- 実装範囲:
  - 同値Observationを重複追加しない。
  - 収集経路ごとに情報量が多いObservationを優先する。
  - 1集約ログあたりのObservation上限を8件とする。
  - Occurrence Count、初回・最終時刻、原文、StackTraceを維持する。
  - 変更のないObservation Collectionを再利用できる経路を設ける。
- 実装対象外: C#重複統合、Rule DB、Corpus。
- 検証方法:
  - 同一ログ10,000件でOccurrence Countが10,000、Observationが8件以下であること。
  - 情報量が多いObservationへ正しく置換されること。
- 完了条件: 対象Test成功、既存Store Test成功、Unityコンパイル確認。
- ロールバック条件: 診断情報消失、Occurrence不整合、上限超過、既存表示退行。
- 次に実装可能なTask: `UJCW-030-002`

---

## UJCW-030-002 C# Compilerログ重複統合

- Status: `PENDING`
- 目的: 通常ログ経路とCompilationPipeline経路の同一C#メッセージをtick非依存で統合する。
- 変更予定ファイル:
  - 変更: `Editor/Classification/LogClassifier.cs`
  - 変更: `Editor/Normalization/MessageNormalizer.cs`
  - 変更: `Editor/Collection/EditorLogPump.cs`
  - 変更: `Editor/Aggregation/LogAggregationStore.cs`
  - 変更: `Editor/Model/AggregationKey.cs`
  - 変更: 関連EditMode Test
- 依存Task: `UJCW-030-001`
- 対応要件: FR-036、FR-043、NFR-005、AC-017
- 実装範囲:
  - 通常ログの`error CSxxxx`、`warning CSxxxx`をCSharpCompilerへ分類する。
  - 正規化本文、LogType、Categoryによる副Indexを追加する。
  - 位置なしRecordと一意に互換な位置ありRecordをbatch非依存で統合する。
  - CompilationPipeline側のファイル、行、列、Assemblyを優先する。
  - 異なるファイル・行または複数候補は統合しない。
- 実装対象外: 類似文章統合、Rule DB。
- 検証方法:
  - 別tickの同一Compiler Messageが一行へ統合されること。
  - 異なる診断位置は別行になること。
- 完了条件: 対象Test成功、Unityコンパイル確認。
- ロールバック条件: 誤統合、副Index不整合、保持上限削除後の参照残留。
- 次に実装可能なTask: `UJCW-030-003`

---

## UJCW-030-003 IMGUI一本化

- Status: `PENDING`
- 目的: UI Toolkit二重実装を削除し、Unity標準Console準拠のIMGUI経路だけを残す。
- 変更予定ファイル:
  - 削除候補: `Editor/UI/ConsoleViewBinder.cs`
  - 削除候補: `Editor/UI/*.uxml`
  - 削除候補: `Editor/UI/*.uss`
  - 必要時変更: `Editor/UnityJapaneseConsoleWindow.cs`
  - 必要時変更: `Editor/UI/ConsoleWindowGui.cs`
- 依存Task: `UJCW-030-002`
- 対応要件: FR-046、FR-047、NFR-013、AC-018
- 実装範囲:
  - `OnGUI -> ConsoleWindowGui -> ConsoleLogList`を正式経路とする。
  - UIElements参照と未使用Assetを削除する。
  - 標準ConsoleアイコンとEditorStylesの利用を維持する。
- 実装対象外: Dictionary UI、Corpus UI。
- 検証方法:
  - 削除対象への参照0件。
  - WindowがIMGUIで開くこと。
- 完了条件: 静的検索、Unityコンパイル、Window起動確認。
- ロールバック条件: 参照切れ、コンパイル失敗、Window起動不能。
- 次に実装可能なTask: `UJCW-030-004`

---

## UJCW-030-004 Rule JSON SchemaとManifest

- Status: `PENDING`
- 目的: カテゴリ別Rule Sourceと出典Manifestのデータ契約を確定する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Rules/TranslationRuleDefinition.cs`
  - 新規: `Editor/Translation/Rules/TranslationRuleManifest.cs`
  - 新規: `Editor/Translation/Rules/TranslationSourceDefinition.cs`
  - 新規: `Editor/TranslationRules/manifest.json`
  - 新規: Schema FixtureとTest
- 依存Task: `UJCW-030-003`
- 対応要件: FR-001～FR-012、NFR-008、NFR-009、AC-010、AC-021
- 実装範囲:
  - Match Type、Rule Status、Source ID、Version、Placeholderを定義する。
  - JSON Field名とSchema Versionを固定する。
  - カテゴリ別Folder構成を作成する。
  - 巨大単一ScriptableObjectを作成しない。
- 実装対象外: Parser、DB生成、Importer。
- 検証方法:
  - 有効・無効JSON FixtureのDeserialize確認。
  - Rule IDとSource IDの必須性確認。
- 完了条件: Schema Test成功、仕様とのField照合完了。
- ロールバック条件: Schema曖昧、既存Ruleを表現不能、Unity Serializer依存発生。
- 次に実装可能なTask: `UJCW-030-005`

---

## UJCW-030-005 Rule ParserとValidator

- Status: `PENDING`
- 目的: Rule Sourceを安全に読み込み、意味的な不正を拒否する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Rules/TranslationRuleParser.cs`
  - 新規: `Editor/Translation/Rules/TranslationRuleValidator.cs`
  - 新規: `Editor/Translation/Rules/TranslationRuleValidationResult.cs`
  - 新規: 関連EditMode Test
- 依存Task: `UJCW-030-004`
- 対応要件: FR-003～FR-012、NFR-008、NFR-011、AC-010
- 実装範囲:
  - Rule ID重複検出。
  - Source ID未解決検出。
  - 空訳、空Match、Placeholder不一致検出。
  - Rule Status検証。
  - Pattern Anchor、Regex Timeout、危険Pattern検証。
  - Approved以外を本番対象から除外できる結果を返す。
- 実装対象外: Binary DB、Importer、UI。
- 検証方法:
  - 重複、空訳、危険Regex、Source不明、Placeholder不一致Fixtureを拒否する。
- 完了条件: Validator Test成功、Regexが無期限実行されないこと。
- ロールバック条件: 不正Rule通過、正常Rule拒否、既存Rule移行不能。
- 次に実装可能なTask: `UJCW-030-006`

---

## UJCW-030-006 Compiled Rule DBと検索Index

- Status: `PENDING`
- 目的: Rule Sourceを高速検索DBへ変換し、Source変更時だけ再生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Compilation/TranslationDatabaseFormat.cs`
  - 新規: `Editor/Translation/Compilation/TranslationDatabaseCompiler.cs`
  - 新規: `Editor/Translation/Compilation/TranslationDatabaseReader.cs`
  - 新規: `Editor/Translation/Rules/TranslationRuleRepository.cs`
  - 新規: 関連EditMode Test
- 依存Task: `UJCW-030-005`
- 対応要件: FR-013～FR-017、FR-039～FR-042、NFR-005、NFR-006、AC-011～AC-014
- 実装範囲:
  - Source Hash、Schema Version、Compiler Versionを記録する。
  - Exact Dictionaryを構築する。
  - Diagnostic Code Dictionaryを構築する。
  - Category別Template・Pattern Indexを構築する。
  - Temporary File、Read-back Validation、Atomic Replaceを実装する。
  - DB破損時にSourceから再生成する。
- 実装対象外: Corpus、Importer、初期大量Rule。
- 検証方法:
  - 50,000 Exact Ruleの正しい検索。
  - Category外Patternを走査しないこと。
  - 破損DBからのRecovery。
- 完了条件: 対象Test成功、Library生成物がGit管理外であること。
- ロールバック条件: Source破損、既存正常DB消失、全件線形走査。
- 次に実装可能なTask: `UJCW-030-007`

---

## UJCW-030-007 既存ローカルRule移行

- Status: `PENDING`
- 目的: 現行C#定義Catalogをカテゴリ別JSONへ移行する。
- 変更予定ファイル:
  - 変更または削除: `Editor/Translation/TranslationRuleCatalog.cs`
  - 新規: 初期カテゴリJSON
  - 変更: `Editor/Translation/TranslationRuleEvaluator.cs`
  - 変更: 関連Test
- 依存Task: `UJCW-030-006`
- 対応要件: FR-001、FR-005～FR-010、FR-039～FR-042、AC-003～AC-007
- 実装範囲:
  - 既存15RuleをJSONへ移行する。
  - Rule IDと翻訳結果を可能な範囲で維持する。
  - EvaluatorをRepository参照へ変更する。
  - AudioSource例のExact Ruleを追加する。
- 実装対象外: 公開Source大量Import。
- 検証方法:
  - 既存翻訳Testが同一結果を返すこと。
  - AudioSource例が想定日本語になること。
- 完了条件: 既存Test成功、C# Catalogへの本番依存削除。
- ロールバック条件: 翻訳退行、Rule ID消失、原文・Placeholder変形。
- 次に実装可能なTask: `UJCW-030-008`

---

## UJCW-030-008 Untranslated Corpus Store

- Status: `PENDING`
- 目的: 未翻訳ログをローカルへ重複集約して保存する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Corpus/UntranslatedCorpusEntry.cs`
  - 新規: `Editor/Translation/Corpus/UntranslatedCorpusStore.cs`
  - 変更: `Editor/Collection/EditorLogPump.cs`
  - 変更: `Editor/UnityJapaneseConsoleWindow.cs`
  - 新規: 関連EditMode Test
- 依存Task: `UJCW-030-007`
- 対応要件: FR-026～FR-030、NFR-002、NFR-010、AC-007～AC-009
- 実装範囲:
  - 未翻訳時だけCorpusへ登録する。
  - Normalized Message、Category、LogTypeで集約する。
  - Count、First Seen、Last Seenを更新する。
  - 最大20,000件と削除優先順位を実装する。
  - Dirty遅延保存とWindow Close時Flushを実装する。
- 実装対象外: Export、Codex呼び出し、StackTrace全保存。
- 検証方法:
  - 同一未翻訳ログ100回でEntry 1件、Count 100。
  - 保持上限と削除優先順位。
- 完了条件: Test成功、`Library/`保存、外部通信0件。
- ロールバック条件: 重複増殖、原文欠損、保存破損、ログループ。
- 次に実装可能なTask: `UJCW-030-009`

---

## UJCW-030-009 Corpus ExportとCoverage UI

- Status: `PENDING`
- 目的: 未翻訳ログを辞書候補として出力し、翻訳率を可視化する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Corpus/UntranslatedCorpusExporter.cs`
  - 変更: `Editor/UI/ConsoleWindowGui.cs`
  - 変更: `Editor/UI/ConsoleLogList.cs`
  - 新規: 関連Test
- 依存Task: `UJCW-030-008`
- 対応要件: FR-031～FR-033、FR-048～FR-053、AC-009
- 実装範囲:
  - JSONとCSV Export。
  - Codex用構造化JSON。
  - Rule ID候補、Match Type候補、Category、Countを含める。
  - Unique CoverageとOccurrence加重Coverageを表示する。
  - Dictionary Status、Corpus Count、Validation ErrorをToolbarまたはPopupへ表示する。
- 実装対象外: LLM呼び出し、自動Rule承認。
- 検証方法:
  - Export FieldとEscapeの確認。
  - Coverage計算確認。
- 完了条件: Test成功、Unity UI手動確認。
- ロールバック条件: CSV/JSON破損、UI操作不能、全件毎フレーム再計算。
- 次に実装可能なTask: `UJCW-030-010`

---

## UJCW-030-010 Manual Rule Importer

- Status: `PENDING`
- 目的: CSVまたはJSONからCandidate Ruleを生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/ManualRuleImporter.cs`
  - 新規: Import Result Model
  - 新規: 関連Test
- 依存Task: `UJCW-030-009`
- 対応要件: FR-024、FR-025、FR-033、AC-020
- 実装範囲:
  - Original、Japanese、Category、Match Type、Source ID、NotesをImportする。
  - Candidate固定で出力する。
  - Validatorへ渡せるJSONを生成する。
- 実装対象外: Approved化、Web取得。
- 検証方法:
  - 有効CSV/JSON、欠損列、重複、EscapeのFixture。
- 完了条件: Test成功、Candidateのみ生成。
- ロールバック条件: Approved自動生成、Source不明通過、入力上書き。
- 次に実装可能なTask: `UJCW-030-011`

---

## UJCW-030-011 C# Diagnostic Importer

- Status: `PENDING`
- 目的: ローカルRoslynまたは保存済み公式SnapshotからC#診断候補を生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/CSharpDiagnosticImporter.cs`
  - 新規: 固定Source Fixture
  - 新規: 関連Test
- 依存Task: `UJCW-030-010`
- 対応要件: FR-018、FR-019、FR-025、AC-020、AC-021
- 実装範囲:
  - Diagnostic Code、Template、Severity、Version、Source IDを抽出する。
  - 同一Codeの複数Templateを保持する。
  - Candidateとして出力する。
- 実装対象外: Web Scraping、日本語訳の自動生成。
- 検証方法:
  - Fixtureから期待CodeとTemplateが生成されること。
- 完了条件: Test成功、Source Manifest生成確認。
- ロールバック条件: Code誤抽出、Template変数消失、ライセンス未記録。
- 次に実装可能なTask: `UJCW-030-012`

---

## UJCW-030-012 .NET Exception Importer

- Status: `PENDING`
- 目的: ローカル.NET Runtime SourceからException候補を生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/DotNetExceptionImporter.cs`
  - 新規: 固定Source Fixture
  - 新規: 関連Test
- 依存Task: `UJCW-030-011`
- 対応要件: FR-018、FR-020、FR-025、AC-020、AC-021
- 実装範囲:
  - Exception Typeと固定Messageを分離する。
  - Template化可能なMessageをCandidate化する。
  - Source Versionを記録する。
- 実装対象外: 実行時Exception原因分析。
- 検証方法: Fixtureから期待候補が生成されること。
- 完了条件: Test成功、Candidateのみ生成。
- ロールバック条件: 動的Message誤抽出、Source Version欠損。
- 次に実装可能なTask: `UJCW-030-013`

---

## UJCW-030-013 UnityCsReference Importer

- Status: `PENDING`
- 目的: ローカルUnityCsReference Checkoutから公開固定ログ候補を生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/UnityCsReferenceImporter.cs`
  - 新規: C# Source Fixture
  - 新規: 関連Test
- 依存Task: `UJCW-030-012`
- 対応要件: FR-018、FR-021、FR-025、AC-020、AC-021
- 実装範囲:
  - `Debug.Log*`、`LogWarning`、`LogError`、Exception Messageを抽出する。
  - Literal、Interpolation、`string.Format`、単純連結をTemplate候補化する。
  - 安定Templateへ変換不能な動的式は除外する。
- 実装対象外: Unity C++ Engine内部Source、Web Clone。
- 検証方法: FixtureからExact・Template候補が期待どおり生成されること。
- 完了条件: Test成功、Candidateのみ生成。
- ロールバック条件: 動的式誤抽出、Source位置欠損、ライセンス未記録。
- 次に実装可能なTask: `UJCW-030-014`

---

## UJCW-030-014 Unity Package Importer

- Status: `PENDING`
- 目的: Project内Package Sourceから診断候補を生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/UnityPackageImporter.cs`
  - 新規: Package Fixture
  - 新規: 関連Test
- 依存Task: `UJCW-030-013`
- 対応要件: FR-018、FR-022、FR-025、AC-020、AC-021
- 実装範囲:
  - `Packages/`と`Library/PackageCache/`を明示操作時だけ走査する。
  - Package Name、Version、Source IDを記録する。
  - PackageごとにCandidate出力を分離する。
- 実装対象外: 毎Domain Reload自動走査、Web取得。
- 検証方法: 固定Package Fixtureで候補とVersion確認。
- 完了条件: Test成功、通常Window起動時にPackage全走査しないこと。
- ロールバック条件: Editor停止級走査、PackageCache変更、Version誤認識。
- 次に実装可能なTask: `UJCW-030-015`

---

## UJCW-030-015 Shader Diagnostic Importer

- Status: `PENDING`
- 目的: ローカルの公開Shader Compiler資料またはSourceからPattern候補を生成する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Importers/ShaderDiagnosticImporter.cs`
  - 新規: Platform別Fixture
  - 新規: 関連Test
- 依存Task: `UJCW-030-014`
- 対応要件: FR-018、FR-023、FR-025、AC-020、AC-021
- 実装範囲:
  - PlatformとCompilerを区別する。
  - Exact、Template、Pattern候補を生成する。
  - 過度な共通化を避ける。
- 実装対象外: 実Compiler実行、非公開SDK Message。
- 検証方法: DXC、Metal、GLSL Fixtureで分類確認。
- 完了条件: Test成功、Candidateのみ生成。
- ロールバック条件: Platform誤統合、危険Regex生成、Source不明。
- 次に実装可能なTask: `UJCW-030-016`

---

## UJCW-030-016 Source Provenance・License Gate

- Status: `PENDING`
- 目的: Rule Sourceの出典・ライセンス・再配布可否を検証するGateを実装する。
- 変更予定ファイル:
  - 変更: `TranslationRuleValidator.cs`
  - 新規: Source Manifest Validation Test
  - 新規: Documentation
- 依存Task: `UJCW-030-015`
- 対応要件: FR-011、FR-012、FR-033、AC-021
- 実装範囲:
  - Source Version、License、Redistribution Policy必須化。
  - 再配布不可SourceをApproved JSON Commit候補から除外する。
  - Local-only Sourceを識別する。
- 実装対象外: 法的判断の自動化、License本文の取得。
- 検証方法: License不明Fixtureが拒否されること。
- 完了条件: Gate Test成功、Source Manifest表示確認。
- ロールバック条件: License不明RuleのApproved化、Local-only情報の公開出力。
- 次に実装可能なTask: `UJCW-030-017`

---

## UJCW-030-017 初期辞書構築

- Status: `PENDING`
- 目的: 優先度の高い公開診断をApproved Ruleへ登録する。
- 変更予定ファイル:
  - 追加・変更: Category別Rule JSON
  - 追加・変更: Source Manifest
  - 追加: Rule Regression Test
- 依存Task: `UJCW-030-016`
- 対応要件: FR-001～FR-012、Section 19、AC-003～AC-006、AC-021
- 実装範囲:
  - Priority 1のC# Diagnostics、頻出.NET Exception、既存Unity Runtime、Shader Patternを登録する。
  - 翻訳は人間またはCodexレビュー後にApproved化する。
  - Rule CountとSource Versionを記録する。
- 実装対象外: 100%網羅、ライセンス不明Source、非公開SDK。
- 検証方法: Representative Message Regression Test。
- 完了条件: Validation Error 0、Regression Test成功、出典確認完了。
- ロールバック条件: 誤訳、識別子変形、Source不明、競合Rule。
- 次に実装可能なTask: `UJCW-030-018`

---

## UJCW-030-018 大規模負荷・破損Recovery試験

- Status: `PENDING`
- 目的: 数万RuleとCorpus上限で性能・メモリ・Recoveryを検証する。
- 変更予定ファイル:
  - 新規または変更: Load Harness
  - 新規: Rule Database Load Test
  - 新規: Corpus Load Test
  - 新規: 計測結果Document
- 依存Task: `UJCW-030-017`
- 対応要件: NFR-005、NFR-006、AC-011～AC-014、AC-016
- 実装範囲:
  - 50,000 Exact、10,000 Diagnostic、10,000 Template、2,000 Pattern、20,000 Corpusを生成する。
  - Load、Lookup、Rebuild、Memoryを計測する。
  - DB破損Recoveryを検証する。
  - 同一ログ10,000件のObservationを検証する。
- 実装対象外: 実Web接続、Player計測。
- 検証方法: 基準PC、Unity Version、計測手順を記録する。
- 完了条件: Editorが操作不能にならず、アルゴリズム要件を満たし、計測結果が記録されること。
- ロールバック条件: 全件線形走査、無制限メモリ、DB Recovery失敗。
- 次に実装可能なTask: `UJCW-030-019`

---

## UJCW-030-019 Unity Editor手動受け入れ

- Status: `PENDING`
- 目的: v0.3.0の全受け入れ条件をUnity Editor上で確認する。
- 変更予定ファイル:
  - 変更: `Specs/UnityJapaneseConsoleWindow/tasks.md`
  - 新規または変更: 手動検証記録
- 依存Task: `UJCW-030-018`
- 対応要件: AC-001～AC-022
- 実装範囲:
  - Network切断環境で全機能を確認する。
  - Exact、Diagnostic、Template、Pattern、Untranslatedを確認する。
  - Corpus、Export、Coverage、DB Rebuild、Recoveryを確認する。
  - Dark/Light Themeを確認する。
  - 標準Console非侵襲とPlayer分離を確認する。
  - 外部Endpoint、API Key、UnityWebRequest、Reflection、内部APIが0件であることを監査する。
- 実装対象外: 新機能追加。
- 検証方法: 各ACへPass/Fail/Not Testedと根拠を記録する。
- 完了条件: 必須ACがすべてPass、未検証なし、重大Findingなし。
- ロールバック条件: CriticalまたはHigh Finding、コンパイル失敗、データ破損。
- 次に実装可能なTask: なし
