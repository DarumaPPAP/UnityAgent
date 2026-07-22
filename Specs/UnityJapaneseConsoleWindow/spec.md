# UnityJapaneseConsoleWindow 要件定義・仕様書

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.3.0`
- Status: Draft
- SpecPath: `Specs/UnityJapaneseConsoleWindow/spec.md`
- TargetPhase: Phase 2 / 完全ローカル辞書育成型
- LastVerified: 2026-07-23

## 1. 目的

Unity Editorで発生するログ、警告、エラー、例外、C#コンパイルメッセージ、Shaderコンパイルメッセージを収集し、原文を失わずに日本語訳を付与して閲覧できるEditor Windowを提供する。

本機能は、外部翻訳API、課金サービス、API Key、ネットワーク通信を一切必要としない。

公開されているC#、.NET、Unity、Shader、Burst、Package関連の診断情報からローカル翻訳ルールを構築し、実プロジェクトで発生した未翻訳ログを収集して辞書を継続的に育てる。

本機能はUnity標準Consoleを置換または改変せず、標準Consoleと並行して利用する補助Consoleとする。

## 2. 背景

UnityのConsoleへ出力されるメッセージは英語であることが多く、内容の把握に時間がかかる。

一般的な機械翻訳APIは、利用量に応じた費用、課金アカウント、API Key、外部通信、機密情報送信などの問題を持つ。また、無料の非公式翻訳Endpointへ依存すると、利用規約、可用性、仕様変更の問題が発生する。

一方、Unity開発で頻出するログの多くは、次のような公開情報または固定パターンとして扱える。

- C# Compiler Diagnostic Code
- .NET Exception Typeと既知メッセージ
- UnityCsReference内の固定ログ文字列
- Unity公式ドキュメントとIssue Trackerで公開されているメッセージ
- Unity Package内の公開C#ソースと診断コード
- Shader Compilerの公開診断パターン
- プロジェクト内で実際に発生した未翻訳ログ

このため、完全一致、診断コード、テンプレート、パターンの複数方式を組み合わせたローカル辞書と、未翻訳ログの収集・レビュー・追加フローを採用する。

## 3. 基本ゴール

1. Unity Editorで発生した対象ログを専用ウィンドウへ収集できる。
2. 登録済み翻訳ルールに一致するメッセージへ日本語訳を即時付与できる。
3. 外部API、課金、API Key、ネットワーク接続なしで全機能を利用できる。
4. 公開情報から翻訳ルール候補を生成するEditor用Importerを提供できる。
5. 実際に発生した未翻訳ログを重複集約してローカル保存できる。
6. 未翻訳ログを辞書追加候補としてJSONまたはCSVへ出力できる。
7. 原文、StackTrace、ファイル、行、列などの診断情報を保持できる。
8. StackTraceを翻訳せず、Unityから受信した文字列のまま表示できる。
9. ログ種別、カテゴリ、翻訳状態、文字列で絞り込める。
10. 同一ログを集約し、大量ログ時もEditorの操作性を維持できる。
11. 対象ファイルと行番号へ移動できる。
12. Unity標準Console、標準Logger、Playerビルドへ副作用を与えない。
13. 巨大な単一ScriptableObjectへ全ルールを格納しない。
14. ルールの出典、対象バージョン、ライセンス、レビュー状態を追跡できる。

## 4. 非ゴール

次を保証しない。

- Unity Consoleへ出力される全メッセージの100%翻訳
- Unity C++ Engine内部の非公開固定文字列の完全収集
- GPU Driver、OS、Platform SDK、Nintendo Switch、PlayStationなど非公開SDK由来ログの網羅
- Asset Store Packageやプロジェクト固有ログの事前網羅
- 未知文章の一般的な自然言語機械翻訳
- 原因分析、修正方法生成、コード自動修正

公開情報と実際の発生ログから翻訳率を継続的に高めることを目標とし、網羅率100%を完了条件にしない。

## 5. 対象環境

- Unity: `6000.3`系
- Editor: Unity Editor専用
- Primary OS: Windows Editor
- Render Pipeline: 非依存
- URP: 17+環境でも動作対象
- RenderGraph: 直接依存しない
- Player: 対象外
- Namespace: `DarumaPPAP.UnityJapaneseConsoleWindow`
- UI: IMGUI
- UI基準: Unity標準ConsoleWindowに近い構成・操作感
- 表示言語: 日本語優先
- 外部通信: なし
- 外部サービス: なし
- API Key: 不要
- 課金機能: なし

## 6. 用語

### 6.1 原文

Unity、Compiler、Packageなどから受信した未変更のメッセージ文字列。

### 6.2 ログ本文

`Application.LogCallback`の`condition`、またはCompiler Messageの本文に相当する文字列。

### 6.3 StackTrace

`Application.LogCallback`の`stackTrace`に相当する文字列。翻訳対象外とする。

### 6.4 翻訳ルール

英語メッセージまたは診断コードを日本語訳へ変換するローカル規則。

### 6.5 ルール正本

Version Controlで管理する、カテゴリ別に分割されたJSON形式の翻訳ルールファイル群。

### 6.6 コンパイル済みルールDB

ルール正本を検証・正規化し、高速検索用形式へ変換した生成物。`Library/UnityJapaneseConsoleWindow/`配下へ保存し、Git管理対象にしない。

### 6.7 出典Manifest

各ルール群の出典、バージョン、ライセンス、生成方法、最終確認日、ルール件数を記録するファイル。

### 6.8 未翻訳ログCorpus

実プロジェクトで発生し、翻訳ルールへ一致しなかったログを、重複集約してローカル保存したデータ。

### 6.9 辞書候補

未翻訳ログCorpusまたは公開ソースImporterから生成された、未承認の翻訳ルール候補。

### 6.10 技術識別子

型名、メソッド名、Namespace、Shader名、Property名、Keyword、Pass名、LightMode、ファイルパス、GUID、エラーコード、数値など、翻訳で変更してはならない文字列。

## 7. 対象範囲

### 7.1 対象ログ

- `Log`
- `Warning`
- `Error`
- `Assert`
- `Exception`
- C# Compiler Error・Warning
- Unity Shader Compiler Error・Warning
- .NET Exception
- Unity RuntimeとEditorの公開固定メッセージ
- URP
- RenderGraph
- Burst
- Jobs
- Package Manager
- Asset Import
- Unity Package内の公開診断メッセージ
- プロジェクト固有メッセージ

### 7.2 対象機能

- ログ収集
- 日本語訳表示
- 原文・StackTrace保持
- 同一ログ集約
- フィルタ・検索
- ファイル移動
- 分割ルール正本
- ルール検証
- 高速検索DB生成
- 公開ソースImporter
- 未翻訳ログ収集
- 辞書候補Export
- 翻訳カバレッジ表示
- ルール出典追跡

### 7.3 対象外

- 外部翻訳API
- Google Cloud Translation
- DeepL
- Azure Translator
- OpenAIまたは他LLM API
- LibreTranslateサーバー
- ローカル翻訳モデルの同梱
- ネットワーク通信
- API Key管理
- Unity標準Consoleの表示置換
- `Debug.unityLogger`または`ILogHandler`の差し替え
- `UnityEditorInternal.LogEntries`などの内部API利用
- Reflectionによる標準Console操作
- Playerまたは実機からのリモートログ収集
- 標準ConsoleのClear、Collapse、Error Pause状態との同期
- 自動でのWeb Scraping
- 未承認ルールの自動本番反映

## 8. 全体アーキテクチャ

```text
公開ソース / ローカルPackage / 未翻訳Corpus
                    ↓
             Rule Importer
                    ↓
             Candidate Rules
                    ↓ 人間またはCodexがレビュー
           Category Rule JSON
                    ↓
         Rule Validator / Compiler
                    ↓
 Library/UnityJapaneseConsoleWindow/
        CompiledRuleDatabase.bin
                    ↓
       TranslationRuleRepository
         ├─ Exact Dictionary
         ├─ Diagnostic Code Dictionary
         ├─ Template Index
         └─ Category Pattern Index
                    ↓
          Japanese Console表示
```

## 9. ルール正本仕様

### FR-001 分割JSONを正本とする

翻訳ルールはカテゴリ別JSONとしてVersion Controlへ保存する。

推奨構成:

```text
Implementation/UnityJapaneseConsoleWindow/Editor/TranslationRules/
├─ manifest.json
├─ CSharpCompiler/
│  ├─ diagnostics.json
│  └─ templates.json
├─ DotNetRuntime/
│  ├─ exceptions.json
│  └─ messages.json
├─ UnityRuntime/
│  ├─ audio.json
│  ├─ animation.json
│  ├─ physics.json
│  ├─ rendering.json
│  └─ general.json
├─ UnityEditor/
│  ├─ asset-import.json
│  ├─ serialization.json
│  └─ package-manager.json
├─ ShaderCompiler/
│  ├─ hlsl.json
│  ├─ dxc.json
│  ├─ metal.json
│  └─ glsl.json
├─ RenderPipeline/
│  ├─ urp.json
│  └─ rendergraph.json
├─ BurstJobs/
│  ├─ burst.json
│  └─ jobs.json
└─ Project/
   └─ project-specific.json
```

固定絶対パスへ依存せず、Manifest AssetまたはGUID検索でルールルートを解決する。

### FR-002 巨大な単一ScriptableObjectを禁止する

全ルールを一つのScriptableObjectへ格納しない。

ScriptableObjectを使用する場合は、次に限定する。

- ルールManifestの参照
- Editor設定
- 小規模なカテゴリ定義

数千件以上のルール本体を単一`.asset`へシリアライズしない。

### FR-003 ルールSchema

各ルールは最低限以下を持つ。

```json
{
  "ruleId": "UJCW-UNITY-AUDIO-0001",
  "schemaVersion": 1,
  "ruleVersion": 1,
  "category": "UnityRuntime",
  "matchType": "Exact",
  "matchValue": "Attempting to set `time` on an audio source that has a resource assigned that is not a clip is ignored!",
  "japanese": "クリップ以外のリソースが割り当てられているAudioSourceに `time` を設定しようとすると、この操作は無視されます。",
  "placeholders": [],
  "sourceId": "UNITY-PUBLIC-MESSAGE",
  "sourceVersion": "6000.3",
  "reviewStatus": "Approved",
  "notes": ""
}
```

### FR-004 Rule ID

`ruleId`は全ルールで一意とする。

推奨形式:

```text
UJCW-<CATEGORY>-<SUBCATEGORY>-<NUMBER>
```

既存Rule IDを再利用しない。

### FR-005 Match Type

最低限以下を提供する。

- `Exact`
- `DiagnosticCode`
- `Template`
- `Pattern`

評価順は固定する。

1. Exact
2. DiagnosticCode
3. Template
4. Pattern
5. 未翻訳

### FR-006 Exact

原文完全一致を使用する。

Unity固定メッセージなど、文字列が安定している場合に利用する。

### FR-007 DiagnosticCode

`CS0246`、Burst診断コードなど、安定した診断コードをキーにする。

同一コードで複数書式が存在する場合は、追加のTemplate条件を指定できること。

### FR-008 Template

変動部分をPlaceholderとして抽出する。

例:

```text
The type or namespace name '{type}' could not be found
```

日本語:

```text
型または名前空間 `{type}` が見つかりません。
```

Placeholderは技術識別子として原文の文字列を保持する。

### FR-009 Pattern

Exact、DiagnosticCode、Templateで表現できない場合だけ使用する。

Patternは次を満たす。

- 原則として先頭・末尾をAnchorする
- Regex Timeoutを設定する
- Catastrophic Backtrackingの可能性があるPatternを拒否する
- カテゴリ別Indexへ格納する
- 全カテゴリの全Patternを毎ログ走査しない

### FR-010 ルール状態

最低限以下を区別する。

- `Candidate`
- `Reviewed`
- `Approved`
- `Deprecated`
- `Rejected`

実際のConsole翻訳に使用できるのは`Approved`だけとする。

### FR-011 ルール出典

各ルールは`sourceId`を持ち、出典Manifestへ関連付ける。

出典Manifestは最低限以下を持つ。

- Source ID
- Source Name
- Source Type
- Source URLまたはRepository
- Source VersionまたはCommit
- License
- Redistribution Policy
- Importer Version
- Last Verified Date
- Extracted Rule Count

### FR-012 ライセンス確認

公開されているだけでは再配布可能とは限らない。

次の方針を採用する。

- ライセンス上再配布可能なソースだけを正本辞書へ取り込む
- ライセンス不明なソースは自動Commitしない
- 再配布不可の場合はImporter定義だけを保持し、利用者のローカル環境で生成する
- 非公開SDKや契約資料の文字列を公開Repositoryへ追加しない
- 各Source Manifestにライセンス判断を記録する

## 10. コンパイル済みルールDB

### FR-013 生成物の保存先

コンパイル済みDBは次へ保存する。

```text
Library/UnityJapaneseConsoleWindow/CompiledRuleDatabase.bin
```

生成物をGit管理しない。

### FR-014 DB再生成条件

次の場合に再生成する。

- DBが存在しない
- Schema Versionが異なる
- Manifest Hashが異なる
- Rule Source Hashが異なる
- Compiler Versionが異なる
- ユーザーが手動Rebuildを実行した

### FR-015 DB Index

最低限以下を構築する。

```text
Dictionary<string, ExactRule>
Dictionary<string, DiagnosticCodeRuleSet>
Dictionary<E_LOG_CATEGORY, TemplateRuleIndex>
Dictionary<E_LOG_CATEGORY, PatternRuleIndex>
```

ExactとDiagnosticCodeの検索は全件線形走査しない。

### FR-016 読み込み失敗

DBの読み込みに失敗した場合は、例外でWindow全体を停止させず、Rule Sourceから再生成を試みる。

再生成にも失敗した場合は原文表示を継続し、ステータス領域へ失敗理由を表示する。

内部失敗を`Debug.LogError`で再出力してログループを発生させない。

### FR-017 原子的更新

DB生成は一時ファイルへ書き込み、検証成功後に置換する。

途中失敗で既存の正常DBを破損させない。

## 11. 公開ソースImporter

### FR-018 Importerの目的

公開ソースから翻訳ルール候補を生成する。

Importerは候補生成までを担当し、`Approved`ルールへ自動昇格させない。

### FR-019 C# Diagnostic Importer

Microsoft公式Diagnostic DocumentationまたはRoslynの公開ソース・Resourceから、ライセンス条件を満たす範囲で次を抽出する。

- Diagnostic Code
- 英語メッセージTemplate
- Severity
- Category
- 対象Compiler Version
- Source情報

同一Diagnostic Codeに複数Templateがある場合を保持できること。

### FR-020 .NET Exception Importer

公開されている.NET Runtime Sourceまたは公式Documentationから、次の候補を生成する。

- Exception Type
- 固定メッセージ
- Template
- Source Version

Exception Type名だけのルールと、固定本文を含むルールを分離する。

### FR-021 UnityCsReference Importer

ローカルに用意されたUnityCsReference Checkoutを入力として、次の構造を解析する。

- `Debug.Log`
- `Debug.LogWarning`
- `Debug.LogError`
- `LogWarning`
- `LogError`
- 公開C#側でthrowされるException Message

文字列連結、Interpolation、`string.Format`はTemplate候補として抽出する。

動的に組み立てられ、安定したTemplateへ変換できないものは候補から除外する。

### FR-022 Unity Package Importer

ローカルProjectの`Packages/`および`Library/PackageCache/`に存在する公開C#ソースから候補を生成できること。

対象例:

- Burst
- Collections
- Jobs
- URP
- Core RP Library
- Addressables
- Package Manager UIの公開コード

PackageごとにVersionとSource Manifestを分離する。

### FR-023 Shader Diagnostic Importer

公開されているCompiler DocumentationまたはSourceから、ライセンス条件を満たす範囲で診断Pattern候補を生成する。

対象候補:

- DXC
- FXC互換メッセージ
- Metal Shader Compiler
- GLSL Compiler
- SPIR-V Tooling
- Unity Shader Compilerで公開されているメッセージ

Platform固有メッセージを共通Patternへ過度に統合しない。

### FR-024 Manual Importer

CSVまたはJSONから候補をImportできること。

最低限の列:

- Original Message
- Japanese Translation
- Category
- Match Type
- Source ID
- Notes

### FR-025 Importerのネットワーク禁止

Importerは自動でWebへアクセスしない。

入力は次に限定する。

- ローカルCheckout
- ローカルPackage
- ユーザーが事前に保存したファイル
- RepositoryへCommit済みのSource Snapshot

## 12. 未翻訳ログCorpus

### FR-026 未翻訳ログ収集

翻訳ルールへ一致しなかったログを、ローカルCorpusへ記録する。

初期状態で有効とする。

外部送信は行わない。

### FR-027 Corpus保存先

```text
Library/UnityJapaneseConsoleWindow/UntranslatedCorpus.json
```

Git管理対象にしない。

### FR-028 Corpus Entry

最低限以下を保持する。

- Message Hash
- Normalized Message
- Original Message
- Category
- LogType
- First Seen At
- Last Seen At
- Occurrence Count
- Unity Version
- Package NameとVersion（解決可能な場合）
- Project Local判定
- Export Status

StackTrace全体はCorpusへ保存しない。

必要な場合は先頭Frameの型名・メソッド名だけを別フィールドへ保存できる。

### FR-029 Corpus重複集約

同じNormalized Message、Category、LogTypeは一件へ集約する。

発生回数を`OccurrenceCount`へ加算し、発生回数分のEntryを追加しない。

### FR-030 Corpus保持上限

初期上限を20,000件とする。

上限到達時は、次の優先順位で削除候補を決定する。

1. Export済みかつ発生回数が少ない
2. 最終発生日時が古い
3. 発生回数が少ない

削除件数をUIへ表示する。

### FR-031 辞書候補Export

未翻訳ログを次の条件で絞り込み、JSONまたはCSVへExportできること。

- 発生回数
- Category
- LogType
- First Seen
- Last Seen
- Project Local
- Export済み・未Export

ExportデータにはRule ID候補とMatch Type候補を含める。

### FR-032 Codex連携用Export

Codexへ翻訳ルール生成を依頼しやすい構造化JSONを出力する。

ただしUnityJapaneseConsoleWindow自体はCodex、LLM、外部APIを呼び出さない。

### FR-033 候補の承認

ImporterまたはCorpusから生成された候補は、次の検証を通過した後にのみ`Approved`へ変更できる。

- Rule ID重複なし
- Match競合なし
- Placeholder復元成功
- 日本語訳が空でない
- 原文と日本語訳が同一でない
- Pattern Timeoutなし
- 出典情報あり
- Reviewer記録あり

## 13. ログ収集仕様

### FR-034 ウィンドウ起動

メニューから`UnityJapaneseConsoleWindow`を開けること。

ウィンドウは同一Editor内で原則1インスタンスとする。

### FR-035 通常ログ収集

`Application.logMessageReceivedThreaded`を利用する。

受信コールバックでは以下だけを行う。

- 受信文字列の保持
- StackTraceの保持
- LogTypeの保持
- 受信時刻の保持
- スレッドセーフな待機列への追加

コールバック内で以下を行わない。

- Unity Editor API
- UI更新
- 翻訳
- Rule検索
- 正規表現
- ファイルI/O
- Corpus保存
- `Debug.Log`系の再出力
- LINQ

### FR-036 C# Compiler Message

`CompilationPipeline.assemblyCompilationFinished`から、各Assemblyの`CompilerMessage`を受信する。

保持項目:

- Assembly出力パス
- メッセージ種別
- 原文
- ファイル
- 行
- 列

### FR-037 Shader Message

通常ログとして受信したShader関連メッセージを分類する。

対象Shaderを公開APIで解決できる場合は、`ShaderUtil.GetShaderMessages`と`ShaderMessage`で構造化情報を補完する。

### FR-038 メインスレッド処理

待機列の取り込み、分類、正規化、Rule検索、集約、Corpus更新、UI更新はEditorメインスレッド側で行う。

1フレーム内の最大処理件数または処理時間に上限を設ける。

## 14. 翻訳評価仕様

### FR-039 翻訳順序

```text
Exact
  ↓
DiagnosticCode
  ↓
Template
  ↓
Pattern
  ↓
Untranslated
```

### FR-040 技術識別子保持

最低限以下を保持する。

- バッククォート内文字列
- 引用符内識別子
- C# Diagnostic Code
- Asset相対パス
- 絶対パス
- Namespace
- 型名
- メソッド名
- Shader名
- Shader Property
- Shader Keyword
- Pass名
- LightMode
- GUID
- 行番号
- 列番号
- 数値

Placeholder抽出または復元に失敗した場合は、そのルールを適用せず次の評価段階へ進む。

### FR-041 翻訳状態

最低限以下を区別する。

- `EXACT_MATCH`
- `DIAGNOSTIC_CODE_MATCH`
- `TEMPLATE_MATCH`
- `PATTERN_MATCH`
- `UNTRANSLATED`
- `TRANSLATION_FAILED`

### FR-042 翻訳元

最低限以下を表示できること。

- Rule Source ID
- Rule ID
- Rule Version
- Source Version
- Review Status

## 15. 集約・保持仕様

### FR-043 同一ログ集約

同一ログは一行へ集約し、発生回数、初回発生時刻、最終発生時刻を更新する。

集約キーは最低限以下を含む。

- 正規化済み原文
- LogType
- Category
- ファイル
- 行

### FR-044 Observation保持

同一ログの発生回数分、Observationを保持しない。

同一内容のObservationは重複追加しない。

収集経路ごとに最も情報量の多いObservationを少数保持する。

初期上限は1集約ログあたり8件とする。

### FR-045 表示ログ保持上限

初期値として最大10,000表示レコードを保持する。

上限到達時は古い表示レコードから削除する。

## 16. UI仕様

### FR-046 IMGUI一本化

正式UI経路:

```text
UnityJapaneseConsoleWindow.OnGUI
    ↓
ConsoleWindowGui
    ↓
ConsoleLogList
```

UI Toolkit、UXML、USSの未使用実装を残さない。

### FR-047 標準Console準拠

次の3領域で構成する。

1. 上部ツールバー
2. ログ一覧
3. 下部詳細ペイン

`EditorStyles`、標準Consoleアイコン、Unity Themeを優先する。

過剰なカードUI、角丸、影、独自Accent Colorを使用しない。

### FR-048 ツールバー

最低限以下を提供する。

- Clear
- Pause
- Collapse
- Log表示切替
- Warning表示切替
- Error表示切替
- Category Filter
- Translation State Filter
- Search
- Dictionary Status
- Untranslated Corpus

### FR-049 一覧表示

翻訳済み:

```text
1行目: 日本語訳
2行目: StackTrace先頭Frame
```

未翻訳:

```text
1行目: 英語原文
2行目: StackTrace先頭Frame
```

StackTraceがない場合は次へFallbackする。

1. ファイルと行番号
2. 発生元
3. Category
4. 空欄

### FR-050 詳細ペイン

表示順序:

1. 日本語訳
2. 原文
3. StackTrace
4. ファイル位置
5. 翻訳Rule情報
6. 出典情報

### FR-051 右クリックメニュー

最低限以下を提供する。

- 表示内容をコピー
- 原文をコピー
- 詳細をコピー
- ファイルを開く
- 未翻訳Corpusへ記録
- 辞書候補としてExport
- Rule Sourceを表示

### FR-052 Dictionary Status

最低限以下を表示する。

- Rule Source Version
- Compiled DB Version
- Approved Rule Count
- Candidate Rule Count
- Exact Count
- Diagnostic Code Count
- Template Count
- Pattern Count
- Corpus Count
- Translation Coverage
- Last Rebuild Time
- Validation Error Count

### FR-053 Translation Coverage

現在のWindow保持ログについて次を計算する。

```text
翻訳率 = 翻訳済みユニークログ数 / 全ユニークログ数
```

Occurrence Count基準の加重翻訳率も別値として表示できること。

## 17. 非機能要件

### NFR-001 完全無料

本機能の利用に、従量課金、Subscription、Cloud Account、API Keyを必要としない。

### NFR-002 完全ローカル

通常利用、翻訳、Corpus収集、DB生成でネットワーク通信を行わない。

### NFR-003 スレッド安全性

`Application.logMessageReceivedThreaded`の並列呼び出しで競合、破損、例外を発生させない。

### NFR-004 公開API限定

Unity 6000.3で公開されているAPIだけを使用する。

内部API、Reflection、非公開フィールドへの依存を0件とする。

### NFR-005 Editor応答性

- ログ1件ごとに全Ruleを線形走査しない
- ExactとDiagnostic CodeはDictionary検索する
- TemplateとPatternはCategory Indexを使用する
- 毎フレーム全ログを再翻訳しない
- Rule Source変更時だけDB再生成する
- UIは可視行だけを描画する

### NFR-006 大規模辞書

最低限、次の検証データ量で機能する設計とする。

- Exact Rule: 50,000件
- Diagnostic Code Rule: 10,000件
- Template Rule: 10,000件
- Pattern Rule: 2,000件
- Corpus Entry: 20,000件

具体的な読み込み時間、検索時間、メモリ予算は`plan.md`で基準PCとともに確定する。

### NFR-007 データ完全性

日本語訳生成の成否にかかわらず、原文、StackTrace、診断位置を変更しない。

### NFR-008 決定論

同一Rule Source Versionと同一入力からは、同一翻訳結果を返す。

### NFR-009 Git差分

Rule Sourceは人間とCodexが差分レビューしやすい形式とする。

一つのJSONへ全カテゴリを格納しない。

### NFR-010 生成物分離

Compiled DB、Corpus、Import中間生成物を`Library/`へ保存し、Git管理対象へ含めない。

### NFR-011 テスト可能性

次をUIから分離し、EditMode Test可能にする。

- Rule Parser
- Rule Validator
- Rule Compiler
- Exact Index
- Diagnostic Code Index
- Template Matcher
- Pattern Matcher
- Placeholder保護・復元
- Corpus Store
- Coverage計算
- Importer Parser

### NFR-012 保守性

`Manager`、`Controller`、`Util`、`Common`、`Helper`という曖昧な型を導入しない。

### NFR-013 Editor専用分離

本機能をEditor専用Assemblyへ分離し、Playerビルドへ含めない。

## 18. 受け入れ条件

### AC-001 完全オフライン

**検証:** Networkを切断した環境でWindowを開き、翻訳、検索、Corpus記録、DB再生成を実行する。

**合格:** 全機能が動作し、外部接続エラーを発生させない。

### AC-002 課金依存なし

**検証:** Project設定とコードを監査する。

**合格:** API Key、Cloud SDK、課金サービス、外部Endpoint参照が0件である。

### AC-003 Exact翻訳

**検証:** 登録済み固定Unityログを発生させる。

**合格:** Exact Ruleの日本語訳が表示され、Rule IDとSource IDを確認できる。

### AC-004 Diagnostic Code翻訳

**検証:** CS0246など登録済みCompiler Errorを発生させる。

**合格:** Diagnostic Code Ruleが適用され、型名が原文どおり保持される。

### AC-005 Template翻訳

**検証:** Placeholderが異なる同一Templateログを複数発生させる。

**合格:** 一つのTemplate Ruleで翻訳され、各Placeholderが正しく復元される。

### AC-006 Pattern翻訳

**検証:** Pattern Rule対象ログを発生させる。

**合格:** Timeoutなしで翻訳される。

### AC-007 未翻訳Fallback

**検証:** 未登録ログを発生させる。

**合格:** 原文とStackTraceが表示され、`UNTRANSLATED`となる。

### AC-008 Corpus記録

**検証:** 同一未翻訳ログを100回発生させる。

**合格:** Corpus Entryは1件、Occurrence Countは100となる。

### AC-009 Corpus Export

**検証:** 未翻訳ログをJSONとCSVへExportする。

**合格:** Original Message、Category、Count、Rule ID候補、Match Type候補が含まれる。

### AC-010 Rule Validation

**検証:** Rule ID重複、空訳、危険Regex、Placeholder不一致を含む入力を検証する。

**合格:** すべて拒否され、既存DBは破損しない。

### AC-011 DB再生成

**検証:** Rule Sourceを1件追加してRebuildする。

**合格:** Manifest Hashが更新され、新Ruleが検索可能になる。

### AC-012 DB破損Recovery

**検証:** Compiled DBを意図的に破損させる。

**合格:** Rule Sourceから再生成し、Windowが利用可能になる。

### AC-013 大規模Exact検索

**検証:** 50,000件のExact Ruleで検索テストを実行する。

**合格:** 全件線形走査を行わず、正しいRuleを返す。

### AC-014 Pattern Index

**検証:** 複数CategoryへPatternを登録する。

**合格:** 対象Category以外のPatternを走査しない。

### AC-015 StackTrace保持

**検証:** Runtime Errorを発生させる。

**合格:** 日本語訳の下へStackTrace先頭Frameを原文のまま表示する。

### AC-016 Observation上限

**検証:** 同一ログを10,000回発生させる。

**合格:** Occurrence Countは10,000、Observation Countは8以下となる。

### AC-017 C#収集経路統合

**検証:** 同一Compiler Messageを通常ログとCompilationPipelineから受信する。

**合格:** 二重表示されず、構造化情報が多いRecordへ統合される。

### AC-018 IMGUI一本化

**検証:** UI実装を監査する。

**合格:** UXML、USS、未使用UI Toolkit Binderが存在せず、正式UIがIMGUI一系統である。

### AC-019 標準Console非侵襲

**検証:** Window起動前後で同じログを発生させる。

**合格:** Unity標準Consoleの内容、件数、Logger挙動が変化しない。

### AC-020 Importer候補生成

**検証:** テスト用公開Source SnapshotをImporterへ入力する。

**合格:** Candidate Ruleが生成され、Approvedへ自動昇格しない。

### AC-021 出典追跡

**検証:** 翻訳済みログのRule Sourceを表示する。

**合格:** Source Name、Version、License、Rule IDを確認できる。

### AC-022 Player分離

**検証:** Assembly DefinitionとPlayer Compile対象を監査する。

**合格:** Editorコード、Rule Source、Compiled DB生成コードがPlayerへ含まれない。

## 19. 初期データソース優先順位

### Priority 1

- C# Compiler Diagnostic CodeとTemplate
- 現在実装済みのUnity Runtime固定ログ
- `NullReferenceException`など頻出.NET Exception
- 頻出Shader/HLSL Compiler Pattern

### Priority 2

- UnityCsReference固定ログ
- Unity 6000.3で使用中Packageの公開診断ログ
- URP
- RenderGraph
- Burst
- Jobs
- Collections

### Priority 3

- Package Manager
- Asset Import
- Addressables
- Platform別公開Shader Compiler Message
- プロジェクト固有ログ

## 20. 実装フェーズ

### Phase 2-A 基盤修正

- Observation重複保持修正
- C# Compiler収集経路統合
- IMGUI一本化
- 既存ローカルRuleの移行

### Phase 2-B Rule DB

- JSON Schema
- Manifest
- Parser
- Validator
- Compiler
- Binary Cache
- Dictionary Index
- Template Index
- Pattern Index

### Phase 2-C Corpus

- 未翻訳ログ収集
- 重複集約
- 保存上限
- JSON/CSV Export
- Coverage表示

### Phase 2-D Importer

- C# Diagnostic Importer
- UnityCsReference Importer
- Unity Package Importer
- Manual Importer
- Shader Diagnostic Importer

### Phase 2-E 初期辞書構築

- C# Diagnostic
- .NET Exception
- Unity Runtime
- Shader
- URP/RenderGraph
- Burst/Jobs

### Phase 2-F 受け入れテスト

- 大規模Rule負荷試験
- Corpus試験
- DB破損Recovery
- Unity Editor手動試験

## 21. 実装前ゲート

実装へ進む前に次を完了する。

1. `plan.md`更新
2. `tasks.md`更新
3. Rule JSON Schema確定
4. Source Manifest Schema確定
5. ライセンス記録方式確定
6. Binary DB Format確定
7. 大規模辞書の計測条件確定
8. 初期Data Source一覧確定
9. Google Cloud関連Taskの削除
10. 外部通信コードが未実装または削除対象であることの確認

## 22. 参考となる公開ソース区分

本仕様は特定URLを自動取得することを要求しない。

実装計画では、次の公開ソース区分ごとに、実際に利用するRepository、Version、License、Importer方式を確定する。

- Microsoft C# Compiler Diagnostics
- Roslyn公開Source
- .NET Runtime公開Source
- UnityCsReference
- Unity Package公開Source
- Unity公式Documentation
- Unity Issue Tracker
- DXCなど公開Shader Compiler Source

公開情報であっても、再配布可否を確認するまでRule Sourceへ取り込まない。
