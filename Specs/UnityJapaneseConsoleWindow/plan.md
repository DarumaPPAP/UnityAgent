# UnityJapaneseConsoleWindow v0.3.0 Implementation Plan

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.3.0`
- Status: Proposed
- TargetSpec: `Specs/UnityJapaneseConsoleWindow/spec.md` v0.3.0
- BaseBranch: `main`
- RootNamespace: `DarumaPPAP`
- ProductNamespace: `DarumaPPAP.UnityJapaneseConsoleWindow`

## 1. 目的

現行のUnity Editor専用Console実装を、外部API、課金、API Key、ネットワーク通信へ依存しない完全ローカル辞書育成型へ移行する。

次の4系統を一つの処理基盤へ統合する。

1. カテゴリ別JSON翻訳ルール
2. 高速検索用コンパイル済みDB
3. 公開ソースからのCandidate Rule生成
4. 実プロジェクトで発生した未翻訳ログCorpus

このPlanは、責務、所有権、ファイル構成、実装順、検証、Rollbackを定義する。承認前に製品コードを変更しない。

## 2. 現状と先行課題

- 正式UI経路は`UnityJapaneseConsoleWindow.OnGUI -> ConsoleWindowGui -> ConsoleLogList`だが、未使用UI Toolkit実装が残存している可能性がある。
- `LogAggregationStore`は同一ログのOccurrenceごとにObservationを追加・複製し、大量発生時にAllocationが増加する。
- C# Compiler Messageが通常ログ経路とCompilationPipeline経路で別tickに到着した場合、二重表示され得る。
- 翻訳ルールはC#コード内の小規模Catalogであり、数万件規模のルール、出典、Version、レビュー状態を管理できない。
- 未翻訳ログを体系的に収集・Exportする仕組みがない。
- Google Cloud Translation前提の旧PlanとTaskはv0.3.0に適合しないため全面置換する。

Rule DBやImporterより先に、Observation、C#重複統合、IMGUI一本化を完了させる。

## 3. 固定アーキテクチャ

```text
Threaded / Compilation Callback
    -> ThreadedLogInbox
    -> EditorLogPump
    -> Classification / Normalization
    -> TranslationRuleRepository
         -> Exact Dictionary
         -> Diagnostic Code Dictionary
         -> Template Index by Category
         -> Pattern Index by Category
    -> LogAggregationStore
    -> UntranslatedCorpusStore (未翻訳時のみ)
    -> ConsoleWindowGui / ConsoleLogList
```

Rule構築経路:

```text
Local Public Source / Package / Corpus Export
    -> Rule Importer
    -> Candidate Rule JSON
    -> Human / Codex Review
    -> Approved Category JSON
    -> RuleSourceValidator
    -> RuleDatabaseCompiler
    -> Library/UnityJapaneseConsoleWindow/CompiledRuleDatabase.bin
    -> TranslationRuleRepository
```

## 4. 所有権と寿命

### 4.1 UnityJapaneseConsoleWindow

Windowが次を生成・所有する。

- `ThreadedLogInbox`
- `ThreadedLogSubscription`
- `CompilationMessageSubscription`
- `EditorLogPump`
- `TranslationRuleRepository`
- `LogAggregationStore`
- `UntranslatedCorpusStore`
- `ConsoleFilter`
- `ConsoleWindowGui`

OnDisableまたはAssembly Reload前に次を実行する。

- Event購読解除
- 待機Queue停止
- Corpus Dirty Data保存
- Rule DB生成中処理の安全な中断
- File StreamのDispose
- UI参照破棄

mutable static、static event、Singleton、Service Locator、Scene上のControllerを追加しない。

### 4.2 Rule Source

カテゴリ別JSONが翻訳ルールの正本である。

- Version Control対象
- 人間とCodexのレビュー対象
- `Approved`ルールだけ本番検索対象
- Rule IDとSource IDで追跡

### 4.3 Compiled DB

`Library/UnityJapaneseConsoleWindow/CompiledRuleDatabase.bin`へ生成する。

- Git管理対象外
- Source HashとCompiler Versionを保持
- Source変更時だけ再生成
- 一時ファイルへ生成後、検証成功時に原子的置換

### 4.4 Untranslated Corpus

`Library/UnityJapaneseConsoleWindow/UntranslatedCorpus.json`へ保存する。

- Git管理対象外
- 同一ログを重複集約
- 最大20,000件
- Explicit ExportでのみProject外または選択先へ出力

## 5. Rule Source構成

```text
Editor/TranslationRules/
├─ manifest.json
├─ CSharpCompiler/
├─ DotNetRuntime/
├─ UnityRuntime/
├─ UnityEditor/
├─ ShaderCompiler/
├─ RenderPipeline/
├─ BurstJobs/
└─ Project/
```

Rule Rootは固定絶対パスに依存せず、Manifest AssetまたはGUID検索で解決する。

## 6. Rule Model

### 6.1 Match Type

- `Exact`
- `DiagnosticCode`
- `Template`
- `Pattern`

評価順は固定する。

### 6.2 Rule Status

- `Candidate`
- `Reviewed`
- `Approved`
- `Deprecated`
- `Rejected`

`Approved`だけをCompiled DBへ含める。

### 6.3 Source Provenance

Ruleは次を参照する。

- Source ID
- Source Name
- Source Type
- Source URLまたはRepository
- Source VersionまたはCommit
- License
- Redistribution Policy
- Importer Version
- Last Verified Date

ライセンス不明または再配布不可Sourceは、公開Rule SourceへCommitしない。

## 7. Rule Database Compiler

### 7.1 Pipeline

```text
Read Manifest
  -> Read Category JSON
  -> Schema Validation
  -> Semantic Validation
  -> Conflict Detection
  -> Placeholder Validation
  -> Regex Safety Validation
  -> Approved Filter
  -> Index Build
  -> Binary Write to Temporary File
  -> Binary Read-back Validation
  -> Atomic Replace
```

### 7.2 Index

- `Dictionary<string, ExactRule>`
- `Dictionary<string, DiagnosticCodeRuleSet>`
- `Dictionary<E_LOG_CATEGORY, TemplateRuleIndex>`
- `Dictionary<E_LOG_CATEGORY, PatternRuleIndex>`

ExactとDiagnosticCodeを全件線形走査しない。

TemplateとPatternは対象Categoryだけを走査する。

### 7.3 Failure

- 既存正常DBを保持
- Windowは原文表示で継続
- ステータスへValidation Errorを表示
- `Debug.LogError`を使用せずログループを防止

## 8. Importer設計

ImporterはCandidate Rule生成だけを担当する。

### 8.1 CSharpDiagnosticImporter

入力:

- ローカルRoslyn Checkout
- 保存済みMicrosoft Diagnostic Source Snapshot

出力:

- Diagnostic Code
- English Template
- Severity
- Category
- Version
- Source ID

### 8.2 DotNetExceptionImporter

入力:

- ローカル.NET Runtime Checkout
- 保存済み公式Source Snapshot

出力:

- Exception Type
- Fixed Message
- Template
- Source Version

### 8.3 UnityCsReferenceImporter

入力:

- ローカルUnityCsReference Checkout

抽出対象:

- `Debug.Log*`
- `LogWarning`
- `LogError`
- 公開C#側Exception Message
- `string.Format`、Interpolation、文字列連結から安定Templateへ変換可能なもの

### 8.4 UnityPackageImporter

入力:

- `Packages/`
- `Library/PackageCache/`

PackageとVersionごとにCandidateとSource Manifestを分離する。

### 8.5 ShaderDiagnosticImporter

入力:

- ローカルCompiler Source Checkout
- 保存済み公式診断資料

Platform固有Messageを過度に共通化しない。

### 8.6 ManualRuleImporter

CSVまたはJSONをCandidate Ruleへ変換する。

### 8.7 Network Boundary

ImporterはWebへ接続しない。

Download、Clone、Web ScrapingはImporterの責務外とする。

## 9. Untranslated Corpus

未翻訳時に次を記録する。

- Message Hash
- Normalized Message
- Original Message
- Category
- LogType
- First Seen At
- Last Seen At
- Occurrence Count
- Unity Version
- Package NameとVersion
- Project Local判定
- Export Status

同一ログの発生回数分Entryを追加しない。

Corpus ExportはJSONとCSVを提供する。

Codex用JSONにはRule ID候補、Match Type候補、Category、Countを含める。

## 10. UI設計

正式UIはIMGUIのみとする。

```text
UnityJapaneseConsoleWindow.OnGUI
    -> ConsoleWindowGui
    -> ConsoleLogList
```

構成:

1. 上部Toolbar
2. 可視行だけ描画するログ一覧
3. 可変高さDetail Pane

Toolbar追加項目:

- Dictionary Status
- Untranslated Count
- Coverage
- Corpus Export
- Rule DB Rebuild

一覧:

- 1行目: 日本語訳、なければ原文
- 2行目: StackTrace先頭Frame、なければファイル位置など

詳細:

- 日本語訳
- 原文
- StackTrace
- 診断位置
- Rule ID
- Source ID
- Rule Version
- Source Version
- License

## 11. 性能設計

検証規模:

- Exact: 50,000
- DiagnosticCode: 10,000
- Template: 10,000
- Pattern: 2,000
- Corpus: 20,000

禁止:

- ログごとの全Rule線形走査
- 毎フレーム全ログ再翻訳
- 毎フレームRule Source再読込
- 同一ログ発生回数分のObservation保持
- 同一未翻訳ログ発生回数分のCorpus Entry保持

具体的な時間・メモリBudgetは基準PCで計測して`tasks.md`の負荷試験Taskで確定する。

## 12. ファイル配置

候補:

```text
Editor/
├─ Aggregation/
├─ Classification/
├─ Collection/
├─ Model/
├─ Translation/
│  ├─ Rules/
│  │  ├─ TranslationRuleDefinition.cs
│  │  ├─ TranslationRuleManifest.cs
│  │  ├─ TranslationRuleParser.cs
│  │  ├─ TranslationRuleValidator.cs
│  │  └─ TranslationRuleRepository.cs
│  ├─ Compilation/
│  │  ├─ TranslationDatabaseCompiler.cs
│  │  ├─ TranslationDatabaseReader.cs
│  │  └─ TranslationDatabaseFormat.cs
│  ├─ Importers/
│  │  ├─ CSharpDiagnosticImporter.cs
│  │  ├─ DotNetExceptionImporter.cs
│  │  ├─ UnityCsReferenceImporter.cs
│  │  ├─ UnityPackageImporter.cs
│  │  ├─ ShaderDiagnosticImporter.cs
│  │  └─ ManualRuleImporter.cs
│  └─ Corpus/
│     ├─ UntranslatedCorpusStore.cs
│     ├─ UntranslatedCorpusEntry.cs
│     └─ UntranslatedCorpusExporter.cs
├─ UI/
└─ Tests/EditMode/

Editor/TranslationRules/
├─ manifest.json
└─ category folders
```

曖昧な`Manager`、`Controller`、`Util`、`Common`、`Helper`を型名に使用しない。

## 13. 実装PhaseとRollback

1. Observation集約・Allocation修正
2. C#コンパイル重複統合
3. IMGUI一本化
4. Rule JSON SchemaとManifest
5. Rule ParserとValidator
6. Compiled DBとIndex
7. 既存Rule移行
8. Untranslated Corpus
9. Corpus ExportとCoverage UI
10. Manual Importer
11. C# Diagnostic Importer
12. .NET Exception Importer
13. UnityCsReference Importer
14. Unity Package Importer
15. Shader Diagnostic Importer
16. 初期辞書構築
17. 大規模負荷試験
18. Unity Editor手動受け入れ

各Phaseは独立Taskとして実装する。

次の場合は当Taskの差分だけRollbackし、Taskを`PENDING`のまま停止する。

- PublicまたはSerialized契約の予期しない破壊
- 内部APIまたはReflectionが必要になる
- 外部通信またはAPI Key依存が追加される
- Editorコンパイル失敗
- Rule SourceまたはCompiled DB破損
- Corpusで原文が欠損
- 既存受け入れ条件の退行

## 14. 検証方針

- 各Taskで対象EditMode Testを追加する。
- Importer Testは固定した小規模Source Fixtureを使用する。
- 自動テストからWebへ接続しない。
- 10,000件同一ログでOccurrence CountとObservation上限を確認する。
- 50,000 Exact RuleでDictionary検索を確認する。
- Compiled DB破損とSourceからのRecoveryを確認する。
- Regex Timeoutと危険Pattern拒否を確認する。
- Static Searchで外部Endpoint、API Key、UnityWebRequest、内部API、Reflectionが0件であることを確認する。
- 実施していないUnity Editor手動確認を完了済みと表現しない。

## 15. 承認ゲート

- 本Planと`tasks.md`の承認前は製品コードを変更しない。
- 承認後も依存を満たす未完了Taskを原則1件ずつ実装する。
- Source Licenseが未確認のRule群をRepositoryへCommitしない。
- Candidate Ruleを自動でApprovedへ昇格させない。
- Google Cloud関連の旧Taskと旧コードを実装しない。
