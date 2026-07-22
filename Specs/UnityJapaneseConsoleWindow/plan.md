# UnityJapaneseConsoleWindow v0.2.0 Implementation Plan

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.2.0`
- Status: Proposed
- TargetSpec: `Specs/UnityJapaneseConsoleWindow/spec.md` v0.2.0
- BaseBranch: `main`
- RootNamespace: `DarumaPPAP`
- ProductNamespace: `DarumaPPAP.UnityJapaneseConsoleWindow`

## 1. 目的

現行のUnity Editor専用Console実装を、原文・StackTrace・診断位置を失わず、ローカル翻訳、Google翻訳Cache、Google Cloud Translation Basic API v2の順で未知ログを日本語化できるv0.2.0へ移行する。

このPlanは実装順序、責務、所有権、通信境界、秘密情報境界、検証とRollbackを確定する。承認前に製品コードを変更しない。

## 2. 現状と先行課題

- 正式UI経路は既に`UnityJapaneseConsoleWindow.OnGUI`から`ConsoleWindowGui`、`ConsoleLogList`へ接続されているが、未使用の`ConsoleViewBinder.cs`、UXML、USSが残存している。
- `LogAggregationStore`は同一ログのOccurrenceごとにObservationを追加・複製し、同一ログ大量発生時にObservation数とAllocationが増加する。
- C#コンパイルログの位置補完統合が同じPump batch内に限定され、通常ログ経路とCompilationPipeline経路が別tickの場合に重複し得る。
- 翻訳状態はローカル翻訳だけを表し、Cache、Google待機、成功、通信失敗、Provider診断情報を保持できない。
- Google送信用Sanitizer、Cache、非秘密設定、API Key解決、Provider、Queue、Result適用は未実装である。

Google翻訳実装より先にObservation、C#重複統合、IMGUI一本化を独立Taskで完了させる。

## 3. 固定アーキテクチャ

処理経路は次に固定する。

```text
Threaded / Compilation Callback
    -> ThreadedLogInbox
    -> EditorLogPump (main thread, 200件または2ms/tick)
    -> Classification / Normalization
    -> TranslationResolutionPipeline
         -> Local Rule
         -> TranslationCacheStore
         -> GoogleTranslationQueue
    -> LogAggregationStore
    -> TranslationResultApplier
    -> ConsoleWindowGui / ConsoleLogList
```

### 3.1 ObservationとC#重複統合

- Collapsed Recordは`E_LOG_SOURCE`ごとに最も情報量の多いObservationを1件だけ保持し、全体最大3件とする。
- Observationの優先度は収集経路、ファイル、行、列、Assembly、Shader Platform、MessageDetails、StackTraceの取得数で決める。
- 同一経路の同値Observationは追加せず、より情報量が多い場合だけ置換する。
- 通常ログにC#コンパイラ形式を認識した場合は`CSHARP_COMPILER`へ分類する。
- 正規化本文、LogType、カテゴリを副Indexとし、tickを跨いで位置なしRecordと位置ありRecordを統合する。
- 複数の互換候補または異なるファイル・行の競合がある場合は推測統合しない。

### 3.2 翻訳モデル

- 既存enum値を維持し、`E_TRANSLATION_STATE`末尾へ`CACHE_MATCH`、`GOOGLE_PENDING`、`GOOGLE_TRANSLATED`、`GOOGLE_FAILED`を追加する。
- `E_TRANSLATION_SOURCE`は`NONE`、`LOCAL_RULE`、`GOOGLE_CACHE`、`GOOGLE_CLOUD_TRANSLATION`を持つ。
- `LogRecord`へSource Message Hash、Provider ID、完了時刻、HTTP Status、Retry回数、最終試行時刻、Request時間、失敗理由を追加する。
- 翻訳更新は不変Recordの置換で行い、Display ID、OccurrenceCount、発生時刻、Observation、Aggregation Keyを維持する。
- 翻訳優先順位は完全一致、エラーコード、パターン、Google Cache、Google API、原文で固定する。

### 3.3 Source Message HashとSanitizer

- `TechnicalIdentifierProtector`はローカル翻訳用として維持する。
- `ExternalTranslationSanitizer`はGoogle送信専用とし、パス、GUID、URL、メール、IP、C#コード、型、Namespace、メソッド、Shader識別子、Instance IDなどを`__UJCW_TOKEN_0000__`形式へ置換する。
- Responseで必須Tokenの不足、重複、順序変更、改変、未知Token、空結果を検出した場合はFail Closedとし、翻訳結果を採用しない。
- Source Message Hashは原文、`en`、`ja`、Sanitizer Version、Provider Options Versionを長さ付きUTF-8列へ正規化し、SHA-256小文字16進文字列で生成する。
- StackTrace、ファイル、行、列、Assembly、Shader Platform、MessageDetails、Project情報はHash、Sanitize、Payloadの対象外とする。

### 3.4 Cache、設定、秘密情報

- Cache保存先は`Library/UnityJapaneseConsoleWindow/GoogleTranslationCache.json`とする。
- CacheはHash、日本語訳、言語、Version、CreatedAtUtc、LastUsedAtUtcだけを保存し、原文、StackTrace、パス、API Keyを保存しない。
- 最大5,000件、LastUsedAtUtcによるLRU削除、Dirty後2秒の遅延保存とする。
- Window CloseとAssembly Reload前にDirty Cacheを保存する。破損・Version不一致Cacheは利用せず、原文表示を継続する。
- 非秘密設定だけをEditorPrefsへ保存し、自動翻訳初期値はOFFとする。
- API KeyはWindow寿命のメモリ入力を優先し、次に`UJCW_GOOGLE_TRANSLATE_API_KEY`を参照する。
- API Keyをソース、Assets、EditorPrefs、Cache、ログ、例外、Status、Tooltipへ含めない。

### 3.5 Google ProviderとQueue

- Endpointは`POST https://translation.googleapis.com/language/translate/v2`だけを使用する。
- JSONは`q`、`source=en`、`target=ja`、`format=text`を持ち、API Keyは`x-goog-api-key` Headerへ設定する。
- `UnityWebRequest`、`UploadHandlerRaw`、`DownloadHandlerBuffer`を使用し、URL QueryへKeyを追加しない。
- Queue初期値は最大16メッセージ、実JSON Payload 32KiB、同時Request 1、最大待機100msとする。
- 同じSource Message HashをCache、Queue、Retry待機、通信中へ重複登録しない。
- Connection Error、HTTP 429、HTTP 500～599だけを1秒、2秒、4秒後に最大3回Retryする。初回を含む最大通信回数は4回とする。
- HTTP 400、401、403、JSON解析、件数不一致、Token復元失敗はRetryしない。
- Pause中は新規Requestを開始せず、通信完了結果はResult Inboxへ保持してResume後に適用する。

### 3.6 UIとライフサイクル

- UIはIMGUIだけを残し、Unity標準Consoleに近いToolbar、可視行一覧、可変Detail Paneを維持する。
- Googleメニューは自動翻訳、Password Field、Key取得元、接続テスト、Cache件数、Cache消去を提供する。
- 一覧1行目は利用可能な日本語訳、なければ原文とする。2行目はStackTrace先頭行を優先し、なければファイル位置、発生時刻、収集経路、カテゴリの順でFallbackする。
- 詳細とCopyは日本語訳、原文、StackTrace、位置、翻訳元、状態、Rule ID、Provider ID、Cache Hit、Request時間、失敗理由を区別する。
- `UnityJapaneseConsoleWindow`がPipeline、Sanitizer、Cache、Settings、Secret、Provider、Queue、Result Inbox、Result Applierを所有する。
- OnDisable、Window Close、Assembly Reload前に受付停止、Request Abort・Dispose、Dirty Cache保存、API Key破棄、updateとイベント購読解除を行う。
- mutable static、static event、Singleton、Service Locator、Reflection、内部Console API、Player向け通信コードを追加しない。

## 4. ファイル配置

- `Editor/Translation/TranslationResolutionPipeline.cs`: 翻訳優先順位と候補判定。
- `Editor/Translation/ExternalTranslationSanitizer.cs`: 外部送信用Token化、検証、復元。
- `Editor/Translation/SourceMessageHash.cs`: Version込みSHA-256生成。
- `Editor/Translation/Cache/TranslationCacheStore.cs`: Cache読込、検索、追加、LRU、Dirty保存。
- `Editor/Translation/Settings/TranslationSettingsStore.cs`: 非秘密EditorPrefs。
- `Editor/Translation/Settings/TranslationSecretResolver.cs`: セッションKeyと環境変数。
- `Editor/Translation/Google/IGoogleTranslationProvider.cs`: Providerと通信Operation契約。
- `Editor/Translation/Google/GoogleTranslationProvider.cs`: Basic v2通信。
- `Editor/Translation/Google/GoogleTranslationDtos.cs`: 内部Wire DTOと結果型。
- `Editor/Translation/Google/GoogleTranslationQueue.cs`: 重複排除、Batch、Retry、Request監視。
- `Editor/Translation/Google/GoogleTranslationResultInbox.cs`: 完了結果の待機列。
- `Editor/Translation/TranslationResultApplier.cs`: Storeの同一Display ID更新。
- Fake ProviderはEditMode Test Assembly内だけに置く。

## 5. 実装PhaseとRollback

1. Observation集約・Allocation修正。
2. C#コンパイル重複統合。
3. IMGUI一本化。
4. 翻訳状態・ログモデル拡張。
5. 外部送信用SanitizerとHash。
6. Google翻訳Cache。
7. 非秘密設定とAPI Key解決。
8. GoogleTranslationProvider。
9. Queue、Batch、Retry、Result Inbox。
10. TranslationResolutionPipelineとStore適用。
11. IMGUI Google設定・状態表示。
12. EditMode統合テスト。
13. Unity Editor手動受け入れ。

各Phaseは`tasks.md`の1 Taskとして実装し、依存Taskと完了条件を満たすまで次へ進まない。公開・serialized契約の予期しない変更、内部APIまたはReflectionの必要化、API Keyまたは診断情報の漏洩、Editorコンパイル失敗、既存受け入れ条件の退行が発生した場合は当Taskの差分だけをRollbackし、Taskを`PENDING`のまま停止する。

## 6. 検証方針

- 各実装Taskで対象EditMode Testを追加・実行する。
- Fake Providerで通信成功、失敗、Retry、遅延、件数不一致、Token破損を再現する。
- 自動テストから実際のGoogle APIへ接続しない。
- 10,000件同一ログでOccurrenceCount、Observation上限、保持上限、検索更新を検証する。
- 静的検索で内部API、Reflection、mutable static、API Key文字列、Player Assembly混入が0件であることを確認する。
- Unityコンパイル、Editor実行、実Google通信、Dark/Light Themeは手動Taskで個別に記録する。
- 実施していない検証を完了済みと表現しない。

## 7. 承認ゲート

- 本Planと`tasks.md`の承認前は製品コードを変更しない。
- 承認後も依存を満たす未完了Taskを原則1件ずつ実装する。
- 実Google通信を実施していない場合は、最終報告へ必ず未検証と記載する。