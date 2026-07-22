# UnityJapaneseConsoleWindow v0.2.0 Tasks

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.2.0`
- Status: Proposed
- Plan: `Specs/UnityJapaneseConsoleWindow/plan.md`
- TargetRoot: `Assets/__MyRepository/JapaneseConsoleWindow`
- RootNamespace: `DarumaPPAP`

## 実行規則

- 全Taskの初期状態は`PENDING`とする。
- 依存Taskが`COMPLETED`である未完了Taskを、原則1件ずつ実装する。
- Task内でコンパイル成立に不可欠な関連ファイルだけは、明記範囲内で同時変更できる。
- EditMode Test成功だけではUnity Editor手動確認が必要なTaskを完了にしない。
- 実Google通信を自動テストから呼ばない。
- 完了条件をすべて満たした場合だけ当Taskを`COMPLETED`へ更新する。
- 停止条件に該当した場合は製品コードの追加変更を止め、Blocker、影響FR/NFR/AC、推奨仕様変更、製品コード変更有無を報告する。

---

## UJCW-020-001 Observation集約・Allocation修正

- Status: `PENDING`
- 目的: 同一ログのOccurrenceごとにObservationが増殖・複製される問題を解消する。
- 変更予定ファイル:
  - 変更: `Editor/Aggregation/LogAggregationStore.cs`
  - 変更: `Editor/Model/LogRecord.cs`
  - 変更: `Editor/Tests/EditMode/LogAggregationStoreTests.cs`
  - 変更: `Editor/Tests/EditMode/LogModelTests.cs`
- 依存Task: なし
- 対応要件: FR-035、FR-038、NFR-005、NFR-011、AC-017
- 実装範囲:
  - Collapsed Recordは収集経路ごとに最も情報量の多いObservationを1件だけ保持する。
  - 全Observation上限を3件とし、同値Observationを追加しない。
  - 同一経路でより構造化情報が多いObservationだけを置換する。
  - OccurrenceCount、初回・最終時刻、原文、StackTrace取得可能性を維持する。
  - 不変Record更新時に変更のないObservation Collectionを再利用できる経路を設ける。
- 実装対象外: 集約キー変更、C#重複統合、翻訳モデル変更。
- 検証方法:
  - 同一ログ10,000件を投入し、OccurrenceCountが10,000、Collapsed Recordが1件、Observationが3件以内であること。
  - 同じ収集経路の情報量が多いObservationへ置換されること。
  - StackTraceやAssemblyを持つ別経路Observationが上限内で保持されること。
- 完了条件: 対象EditMode Test成功、既存Store Test成功、Unityコンパイル確認。
- ロールバック条件: Observation上限超過、取得済み診断情報の消失、OccurrenceCount不整合、既存表示の退行。
- 次に実装可能なTask: `UJCW-020-002`

---

## UJCW-020-002 C#コンパイルログ重複統合

- Status: `PENDING`
- 目的: 通常ログ経路とCompilationPipeline経路で取得した同一C#メッセージをtick非依存で統合する。
- 変更予定ファイル:
  - 変更: `Editor/Classification/LogClassifier.cs`
  - 変更: `Editor/Normalization/MessageNormalizer.cs`
  - 変更: `Editor/Collection/EditorLogPump.cs`
  - 変更: `Editor/Aggregation/LogAggregationStore.cs`
  - 変更: `Editor/Model/AggregationKey.cs`
  - 変更: `Editor/Tests/EditMode/LogAggregationStoreTests.cs`
  - 変更: `Editor/Tests/EditMode/LogClassifierTests.cs`
  - 変更: `Editor/Tests/EditMode/EditorLogPumpTests.cs`
- 依存Task: `UJCW-020-001`
- 対応要件: FR-003、FR-034、NFR-005、NFR-014、AC-016
- 実装範囲:
  - 正規化済みC#コンパイラ形式を通常ログでも`CSHARP_COMPILER`へ分類する。
  - 正規化本文、LogType、カテゴリによる副IndexをStoreへ追加する。
  - 位置なしRecordと一意に互換な位置ありRecordをbatch IDに依存せず統合する。
  - CompilationPipeline側のファイル、行、列、AssemblyをPrimary Observationとして優先する。
  - 異なるファイル・行、または複数候補がある場合は統合しない。
  - 副IndexをClearと保持上限削除に追従させる。
- 実装対象外: 異なる原文の類似検索、標準Console内部情報、Reflection。
- 検証方法:
  - 別tickで通常ログと構造化Compiler Messageを投入し1行へ統合されること。
  - ファイルと行が異なる同文メッセージは別行になること。
  - 曖昧な位置なしメッセージを推測統合しないこと。
- 完了条件: 対象EditMode Test成功、既存分類・正規化・Store Test成功、Unityコンパイル確認。
- ロールバック条件: 異なる診断位置の誤統合、副Index不整合、保持上限削除後の参照残留。
- 次に実装可能なTask: `UJCW-020-003`

---

## UJCW-020-003 IMGUI一本化

- Status: `PENDING`
- 目的: 未使用UI Toolkit実装を削除し、正式UI経路をIMGUIだけにする。
- 変更予定ファイル:
  - 削除: `Editor/UI/ConsoleViewBinder.cs`
  - 削除: `Editor/UI/UnityJapaneseConsoleWindow.uxml`
  - 削除: `Editor/UI/UnityJapaneseConsoleWindow.uss`
  - 必要時のみ変更: `Editor/UnityJapaneseConsoleWindow.cs`
- 依存Task: `UJCW-020-002`
- 対応要件: FR-039、FR-049、FR-053、NFR-003、AC-001、AC-020、AC-021
- 実装範囲:
  - `OnGUI -> ConsoleWindowGui -> ConsoleLogList`だけを正式UI経路として残す。
  - UXML、USS、UIElements参照が製品Assemblyへ残っていないことを確認する。
- 実装対象外: Google UI、既存IMGUIのデザイン変更、標準Console同期。
- 検証方法:
  - 削除対象への参照検索が0件であること。
  - Editor Assemblyがコンパイルし、ウィンドウがIMGUIで開くこと。
  - Player Assembly対象へ含まれないこと。
- 完了条件: 静的検索、Unityコンパイル、ウィンドウ起動確認。
- ロールバック条件: 参照切れ、Editorコンパイル失敗、IMGUIウィンドウ起動不能。
- 次に実装可能なTask: `UJCW-020-004`

---

## UJCW-020-004 翻訳状態・ログモデル拡張

- Status: `PENDING`
- 目的: CacheとGoogle非同期翻訳を同じDisplay IDへ適用できる不変モデルと契約を追加する。
- 変更予定ファイル:
  - 変更: `Editor/Model/LogModelEnums.cs`
  - 変更: `Editor/Model/LogRecord.cs`
  - 新規: `Editor/Model/TranslationMetadata.cs`
  - 新規: `Editor/Translation/Google/IGoogleTranslationProvider.cs`
  - 新規: `Editor/Translation/Google/GoogleTranslationDtos.cs`
  - 変更: `Editor/Tests/EditMode/LogModelTests.cs`
- 依存Task: `UJCW-020-003`
- 対応要件: FR-007、FR-008、FR-009、FR-010、FR-019、FR-036、NFR-006、NFR-011、NFR-012
- 実装範囲:
  - 既存`E_TRANSLATION_STATE`数値を維持し、末尾へ`CACHE_MATCH`、`GOOGLE_PENDING`、`GOOGLE_TRANSLATED`、`GOOGLE_FAILED`を追加する。
  - `E_TRANSLATION_SOURCE`へ`NONE`、`LOCAL_RULE`、`GOOGLE_CACHE`、`GOOGLE_CLOUD_TRANSLATION`を定義する。
  - Source Message Hash、Provider ID、完了時刻、HTTP Status、Retry回数、最終試行時刻、Request時間、失敗理由を保持する。
  - Display ID、Occurrence、時刻、Observation、Aggregation Keyを維持する不変翻訳更新を追加する。
  - Provider Batch Request、Operation、Batch Resultの最小契約を確定する。
- 実装対象外: 通信、Queue、Cache I/O、UI。
- 検証方法:
  - 既存enum値が変化しないこと。
  - 翻訳更新後もDisplay IDと集約情報が一致すること。
  - 未翻訳のdefault metadataが有効であること。
- 完了条件: Model Test成功、公開・serialized互換性監査、Unityコンパイル確認。
- ロールバック条件: enum値変更、既存constructor利用箇所の破壊、原文・StackTraceの変更。
- 次に実装可能なTask: `UJCW-020-005`

---

## UJCW-020-005 外部送信用SanitizerとHash

- Status: `PENDING`
- 目的: Googleへ送信できる最小本文だけを生成し、技術識別子と機密候補を安全に復元する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/ExternalTranslationSanitizer.cs`
  - 新規: `Editor/Translation/SourceMessageHash.cs`
  - 新規: `Editor/Tests/EditMode/ExternalTranslationSanitizerTests.cs`
  - 新規: `Editor/Tests/EditMode/SourceMessageHashTests.cs`
- 依存Task: `UJCW-020-004`
- 対応要件: FR-012、FR-016、FR-017、FR-018、FR-020、FR-021、NFR-008、NFR-009、NFR-010、AC-007、AC-009、AC-010
- 実装範囲:
  - 指定されたパス、GUID、URL、メール、IP、引用文字列、C#コード、型、Namespace、メソッド、Shader識別子、Instance IDをToken化する。
  - Tokenは`__UJCW_TOKEN_0000__`形式で順序を固定する。
  - Token不足、重複、順序変更、改変、未知Token、空復元を拒否する。
  - 単一本文8KiB、英字、日本語中心、空白、数値のみ、GUIDのみ、パスのみを判定する。
  - 長さ付きUTF-8列からSHA-256小文字16進Hashを生成する。
  - HashとPayloadへStackTrace、診断位置、Project情報を渡さないAPI形状にする。
- 実装対象外: ローカル翻訳用`TechnicalIdentifierProtector`の置換、原因推測。
- 検証方法:
  - 全必須識別子のToken化と完全復元。
  - StackTraceとファイル位置を別引数としても受け取らないこと。
  - Token破損各パターンがFail Closedになること。
  - Version変更でHashが変わり、同一入力で決定論的に一致すること。
- 完了条件: 新規Test成功、セキュリティ境界のコード監査、Unityコンパイル確認。
- ロールバック条件: パス・GUID等の未保護送信可能性、Token誤復元、Hashへ禁止情報が混入。
- 次に実装可能なTask: `UJCW-020-006`

---

## UJCW-020-006 Google翻訳Cache

- Status: `PENDING`
- 目的: Google成功結果をLibrary配下へ安全に保存し、同一Hashの再通信を防ぐ。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Cache/TranslationCacheStore.cs`
  - 新規: `Editor/Translation/Cache/TranslationCacheDtos.cs`
  - 新規: `Editor/Tests/EditMode/TranslationCacheStoreTests.cs`
- 依存Task: `UJCW-020-005`
- 対応要件: FR-026、FR-027、FR-028、FR-029、FR-030、NFR-005、NFR-007、NFR-010、AC-005
- 実装範囲:
  - `Library/UnityJapaneseConsoleWindow/GoogleTranslationCache.json`を使用する。
  - Hash、日本語訳、言語、Version、CreatedAtUtc、LastUsedAtUtcだけを保存する。
  - 最大5,000件を維持し、LastUsedAtUtcが古いEntryから削除する。
  - Hit時にLastUsedAtUtcを更新し、Dirty後2秒でまとめて保存する。
  - Window CloseとAssembly Reload前に強制保存できるAPIを提供する。
  - 不存在、破損、Version不一致は空Cacheとして継続し、内部Debug Logを出さない。
- 実装対象外: Assets保存、クラウド同期、原文保存、API Key保存。
- 検証方法:
  - Hit/Miss、Version不一致、5,001件LRU、Dirty遅延、強制保存。
  - JSONへ原文、StackTrace、パス、API Keyが存在しないこと。
  - 破損JSONから例外を外部へ漏らさず空起動すること。
- 完了条件: Cache Test成功、保存先と内容監査、Unityコンパイル確認。
- ロールバック条件: Assets/Git対象への保存、禁止情報保存、上限超過、破損時のウィンドウ停止。
- 次に実装可能なTask: `UJCW-020-007`

---

## UJCW-020-007 非秘密設定とAPI Key解決

- Status: `PENDING`
- 目的: 非秘密設定とAPI Keyの寿命・保存境界を分離する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Settings/TranslationSettingsStore.cs`
  - 新規: `Editor/Translation/Settings/TranslationSecretResolver.cs`
  - 新規: `Editor/Tests/EditMode/TranslationSettingsStoreTests.cs`
  - 新規: `Editor/Tests/EditMode/TranslationSecretResolverTests.cs`
- 依存Task: `UJCW-020-006`
- 対応要件: FR-031、FR-032、FR-033、NFR-008、AC-013
- 実装範囲:
  - 自動翻訳初期値OFF、Cache容量、Batch最大件数、Toolbar設定だけをEditorPrefsへ保存する。
  - Window寿命のセッション入力を優先し、次に`UJCW_GOOGLE_TRANSLATE_API_KEY`を取得する。
  - Key取得元は`Session`、`Environment`、`Unavailable`だけを返し、値を表示しない。
  - Clear/DisposeでセッションKey参照を破棄する。
- 実装対象外: API Keyの妥当性通信、Project JSON、EditorPrefsへのKey保存。
- 検証方法:
  - 設定default、読込、保存、Key非保存。
  - セッション値優先、環境変数Fallback、未設定。
  - Status、Tooltip、ToString、例外へKeyが含まれないこと。
- 完了条件: Settings/Secret Test成功、秘密情報検索、Unityコンパイル確認。
- ロールバック条件: Key永続化、Key値の表示、環境変数より低い優先順位、Dispose後保持。
- 次に実装可能なTask: `UJCW-020-008`

---

## UJCW-020-008 GoogleTranslationProvider

- Status: `PENDING`
- 目的: Google Cloud Translation Basic API v2との通信をログモデルとUIから分離する。
- 変更予定ファイル:
  - 変更: `Editor/Translation/Google/IGoogleTranslationProvider.cs`
  - 変更: `Editor/Translation/Google/GoogleTranslationDtos.cs`
  - 新規: `Editor/Translation/Google/GoogleTranslationProvider.cs`
  - 新規: `Editor/Tests/EditMode/FakeGoogleTranslationProvider.cs`
  - 新規: `Editor/Tests/EditMode/GoogleTranslationProviderTests.cs`
- 依存Task: `UJCW-020-005`、`UJCW-020-007`
- 対応要件: FR-015、FR-018、FR-020、FR-024、NFR-003、NFR-004、NFR-008、NFR-009、AC-006、AC-007、AC-010、AC-014、AC-015
- 実装範囲:
  - POST Endpoint、UTF-8 JSON、`source=en`、`target=ja`、`format=text`を実装する。
  - API Keyを`x-goog-api-key` Headerだけへ設定する。
  - `UnityWebRequest`を非同期開始し、main threadで完了監視するOperationを返す。
  - HTTP結果、Status Code、Connection Error、Response JSON、件数、空文字を分類する。
  - AbortとDisposeを冪等にする。
  - 内部Wire DTOのGoogle JSON field名は外部公開APIにしない。
- 実装対象外: Queue、Retry、Cache、実Google自動テスト。
- 検証方法:
  - Request生成でURL、Header、Content-Type、JSON、件数を検査する。
  - PayloadへStackTrace、ファイルパス、API Key文字列が含まれないこと。
  - 成功、400、401、403、429、500、Connection Error、JSON失敗、件数不一致をFake Operationで再現する。
- 完了条件: Provider Test成功、禁止情報監査、Unityコンパイル確認。
- ロールバック条件: URL Query Key、秘密情報または診断情報漏洩、Request Dispose漏れ、内部API必要化。
- 次に実装可能なTask: `UJCW-020-009`

---

## UJCW-020-009 Queue・Batch・Retry

- Status: `PENDING`
- 目的: Google Requestの重複排除、Batch、同時数、Retry、ライフサイクルを制御する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/Google/GoogleTranslationQueue.cs`
  - 新規: `Editor/Translation/Google/GoogleTranslationResultInbox.cs`
  - 新規: `Editor/Tests/EditMode/GoogleTranslationQueueTests.cs`
  - 新規: `Editor/Tests/EditMode/GoogleTranslationResultInboxTests.cs`
- 依存Task: `UJCW-020-008`
- 対応要件: FR-021、FR-022、FR-023、FR-024、FR-047、FR-048、FR-051、NFR-004、NFR-005、NFR-010、AC-011、AC-014、AC-015、AC-018、AC-019
- 実装範囲:
  - Cache、待機、Retry、通信中を含むSource Hash重複排除を行う。
  - 最大16件、実JSON 32KiB、最大待機100ms、同時1Requestを適用する。
  - 入力順とResponse順を対応付ける。
  - Connection Error、429、500～599だけを1、2、4秒後に最大3回Retryする。
  - Pause中は新規開始せず、完了結果をResult Inboxに保持する。
  - Clear/Dispose/Assembly Reloadで受付停止、通信中Abort・Dispose、待機Queue消去を行う。
- 実装対象外: Store更新、UI、Cacheファイル削除。
- 検証方法:
  - 同一Hash100回でProvider Start 1回。
  - 16件境界、32KiB境界、100ms Flush、同時1件。
  - Retry間隔、最大4通信、400/401/403非Retry。
  - Pause、Resume、Clear、Dispose、Reload相当。
- 完了条件: Queue/Inbox Test成功、Request Dispose監査、Unityコンパイル確認。
- ロールバック条件: 重複通信、Payload上限超過、Retry対象誤り、Pause/Clear後の予期しない開始、Dispose漏れ。
- 次に実装可能なTask: `UJCW-020-010`

---

## UJCW-020-010 翻訳PipelineとStore適用

- Status: `PENDING`
- 目的: ローカルRule、Cache、Google候補判定と非同期結果を既存Storeへ統合する。
- 変更予定ファイル:
  - 新規: `Editor/Translation/TranslationResolutionPipeline.cs`
  - 新規: `Editor/Translation/TranslationResultApplier.cs`
  - 変更: `Editor/Collection/EditorLogPump.cs`
  - 変更: `Editor/Aggregation/LogAggregationStore.cs`
  - 変更: `Editor/UnityJapaneseConsoleWindow.cs`
  - 新規: `Editor/Tests/EditMode/TranslationResolutionPipelineTests.cs`
  - 新規: `Editor/Tests/EditMode/TranslationResultApplierTests.cs`
- 依存Task: `UJCW-020-001`、`UJCW-020-002`、`UJCW-020-006`、`UJCW-020-007`、`UJCW-020-009`
- 対応要件: FR-011、FR-016、FR-019、FR-025、FR-026、FR-036、NFR-006、NFR-007、NFR-011、AC-004、AC-005、AC-006、AC-011、AC-012、AC-013、AC-016
- 実装範囲:
  - Local Rule、Cache、Google、原文の固定優先順位を適用する。
  - 自動翻訳OFF、Keyなし、不適格本文でQueue登録しない。
  - 手動翻訳だけは自動翻訳OFFを迂回するが、Key、Sanitizer、8KiB等の安全条件は維持する。
  - Google待機を同じDisplay IDの`GOOGLE_PENDING`として表示可能にする。
  - 完了結果を同一HashのCollapsed/Individual Recordへ適用する。
  - Display ID、Occurrence、時刻、Observation、Aggregation Keyを維持し、Search Documentを再構築する。
  - Windowが全翻訳コンポーネントを生成・所有・破棄する。
- 実装対象外: UI操作、複数Provider、標準Console同期。
- 検証方法:
  - Local RuleがCacheとProviderより優先、CacheがProviderより優先。
  - 自動OFFとKeyなしで通信0回。
  - pendingからsuccess/failureへ同じDisplay IDで更新。
  - Collapsed/IndividualとSearch Documentの同時更新。
- 完了条件: Pipeline/Applier Test成功、既存Pump/Store Test成功、Unityコンパイル確認。
- ロールバック条件: 優先順位逆転、新しいログ行追加、Display ID変更、原文・StackTrace変更、オフライン機能停止。
- 次に実装可能なTask: `UJCW-020-011`

---

## UJCW-020-011 IMGUI Google設定・状態表示

- Status: `PENDING`
- 目的: Google翻訳を明示的に制御し、待機・成功・失敗をUnity標準Consoleに近いIMGUIで確認できるようにする。
- 変更予定ファイル:
  - 変更: `Editor/UI/ConsoleWindowGui.cs`
  - 変更: `Editor/UI/ConsoleLogList.cs`
  - 変更: `Editor/UI/ConsoleFilter.cs`
  - 変更: `Editor/UnityJapaneseConsoleWindow.cs`
  - 変更: `Editor/Tests/EditMode/ConsoleFilterTests.cs`
- 依存Task: `UJCW-020-010`
- 対応要件: FR-040、FR-041、FR-042、FR-043、FR-044、FR-045、FR-046、FR-047、FR-048、FR-049、AC-001、AC-006、AC-008、AC-012、AC-013、AC-014、AC-015、AC-018
- 実装範囲:
  - Googleメニューへ自動翻訳、Password Field、Key取得元、接続テスト、Cache件数、Cache消去を追加する。
  - Password Fieldは現在値を再表示せず、Key取得元だけを表示する。
  - 右クリックと詳細へ手動翻訳、再試行、当該Cache削除、原文/日本語表示を追加する。
  - 一覧1行目は日本語訳優先、2行目はStackTrace先頭行優先とする。
  - StackTraceなしの2行目はファイル位置、発生時刻、収集経路、カテゴリの順でFallbackする。
  - 詳細へ翻訳元、状態、Rule ID、Provider ID、Cache Hit、Request時間、HTTP、Retry、失敗理由を追加する。
  - Copyを表示内容、原文、日本語訳、StackTrace、詳細全体に分ける。
  - pending/failedは標準Styleと小さな状態表示で示し、独自アクセント色やカードUIを追加しない。
- 実装対象外: UI Toolkit、標準Console状態同期、API Key表示。
- 検証方法:
  - Dark/Light Theme、狭いWindow幅、可視行描画、選択維持。
  - 翻訳済み/待機/失敗/未翻訳の1・2行表示。
  - 各Copy内容と詳細順序。
  - 自動OFFでも手動翻訳可能、Clearで通信Abort、Cacheは維持。
- 完了条件: Filter Test成功、Unityコンパイル、Editor手動UI確認。
- ロールバック条件: API Key表示、一覧原文/StackTrace喪失、UI Toolkit再導入、標準Console内部依存。
- 次に実装可能なTask: `UJCW-020-012`

---

## UJCW-020-012 EditMode統合テスト

- Status: `PENDING`
- 目的: v0.2.0の通信境界、優先順位、上限、ライフサイクルを実Google通信なしで統合検証する。
- 変更予定ファイル:
  - 変更: `Editor/Tests/EditMode/EditorLogLoadHarness.cs`
  - 変更: `Editor/Tests/EditMode/EditorLogLoadHarnessTests.cs`
  - 変更: `Editor/Tests/EditMode/EditorLogPumpTests.cs`
  - 変更: `Editor/Tests/EditMode/LogSubscriptionLifecycleTests.cs`
  - 変更: `Editor/Tests/EditMode/LogAggregationStoreTests.cs`
  - 変更: Task 004～011で追加した各EditMode Test
- 依存Task: `UJCW-020-011`
- 対応要件: NFR-001～NFR-014、AC-002～AC-021
- 実装範囲:
  - Local/Cache/Google優先順位と通信0回条件。
  - Hash重複排除、Batch件数・Byte数、Retry、Response件数不一致。
  - StackTrace、ファイルパス、API KeyがPayloadへ含まれないこと。
  - Token抽出・復元・不足・重複・未知・改変。
  - Cache Hit、Version、5,000件、LRU、Dirty保存。
  - Store更新後のDisplay ID、Occurrence、Search Document。
  - Window Close/Assembly Reload相当のAbort、Dispose、Event解除。
  - 同一ログ10,000件のObservation上限と保持上限。
  - 内部API、Reflection、mutable static、Player Assembly混入の静的確認。
- 実装対象外: 実Google API、Player実行、実機性能計測。
- 検証方法:
  - Unity Test Runner EditModeで対象Assembly全件を実行する。
  - Fake Providerの通信回数とPayloadを検査する。
  - 既存Testを含むRegressionを確認する。
- 完了条件: 全EditMode Test成功、静的監査0件、Unityコンパイル確認。
- ロールバック条件: 実Google通信の自動呼出し、flakyな時間依存、既存Test退行、秘密情報をTest出力へ含める。
- 次に実装可能なTask: `UJCW-020-013`

---

## UJCW-020-013 Unity Editor手動受け入れ

- Status: `PENDING`
- 目的: Unity 6000.3 Editor上でのみ確認できる動作と外観を受け入れ条件へ対応付ける。
- 変更予定ファイル:
  - 原則なし
  - 検証で不具合が見つかった場合は該当実装Taskを再度`PENDING`へ戻し、そのTask範囲だけを修正する。
- 依存Task: `UJCW-020-012`
- 対応要件: AC-001～AC-021
- 実装範囲:
  - メニュー起動とConsoleエラーなし。
  - Log、Warning、Error、Assert、Exception、別スレッドログ。
  - C#コンパイル、Shaderコンパイル、同一ログ大量発生。
  - Pause、Resume、Clear、Window Close、Assembly Reload。
  - Dark Theme、Light Theme、ファイルジャンプ、Copy。
  - 有効Key、無効Key、Keyなし、ネットワーク切断、AudioSource警告。
  - 実Google通信はユーザーが明示的にKeyを設定して実施した場合だけ記録する。
- 実装対象外: Player、IL2CPP、実機、Google Advanced v3、他Provider。
- 検証方法:
  - ACごとに実施日時、Unity Version、結果、未検証理由を記録する。
  - Request Payloadを確認可能なFake/受入手段でStackTraceと診断情報非送信を確認する。
  - 実Google通信を行わない場合は必ず未検証と記載する。
- 完了条件: 必須ACがすべて合格し、実施できない項目が未検証として明示され、重大Findingが残っていないこと。
- ロールバック条件: Editorコンパイル失敗、例外、購読重複、Request Dispose漏れ、API Key漏洩、標準ConsoleまたはPlayerへの副作用。
- 次に実装可能なTask: なし

---

## 完了報告Template

各Task完了時に次を報告する。

- Task ID / Task名
- Status
- 新規・変更・削除ファイル
- 対応FR / NFR / AC
- 実装した内容
- 実装対象外
- 実施したEditMode Test
- 静的確認
- Unityコンパイル
- Editor実行
- Google実通信
- 未検証事項
- 監査結果: 内部API、Reflection、mutable static、API Key露出、StackTrace外部送信、Editor Assembly分離、Request Dispose、Event解除、Allocation
- 仕様との差異
- 次に実装可能なTask ID