# UnityJapaneseConsoleWindow Decisions

- FeatureName: `UnityJapaneseConsoleWindow`
- Status: Draft
- LastUpdated: 2026-07-23

## D-001 専用Editor Windowとして実装する

Unity標準Consoleの表示置換ではなく、標準Consoleと並行して利用する専用Editor Windowとする。

**理由:** 標準Console内部状態への依存を避け、Unity更新時の互換性リスクを抑えるため。

## D-002 公開APIだけを使用する

通常ログは`Application.logMessageReceivedThreaded`、C#コンパイル情報は`CompilationPipeline.assemblyCompilationFinished`、Shader詳細は解決可能な場合に`ShaderUtil.GetShaderMessages`を使用する。

**理由:** `UnityEditorInternal.LogEntries`やReflectionによる非公開API利用を避けるため。

## D-003 標準Loggerを差し替えない

`Debug.unityLogger`および既存`ILogHandler`を変更しない。

**理由:** 他のツール、Package、プロジェクト固有Loggerの挙動へ副作用を与えないため。

## D-004 ローカル翻訳とGoogle翻訳のハイブリッド方式を採用する

既知ログは承認済みローカル翻訳ルールで変換し、未登録ログだけをGoogle Cloud Translation Basic API v2へ送信する。

翻訳優先順位は次の固定順序とする。

1. 完全一致ルール
2. エラーコードルール
3. パターンルール
4. Google翻訳Cache
5. Google Cloud Translation Basic v2
6. 原文表示

**理由:** 頻出ログの翻訳品質とオフライン動作を維持しつつ、未知ログへ通常の機械翻訳を適用するため。

## D-005 Google翻訳は明示的なOpt-inとする

未知ログの自動Google翻訳は初期状態で無効とする。ユーザーが明示的に有効化した場合だけ外部送信する。

手動の「このログを翻訳」は明示操作として、自動翻訳OFF時でも実行可能とする。

**理由:** ログ本文の外部送信とAPI利用料金をユーザーが制御できるようにするため。

## D-006 Google Cloud Translation Basic API v2を採用する

初期ProviderはGoogle Cloud Translation Basic API v2だけとし、HTTPS RESTと`UnityWebRequest`で呼び出す。

Requestは`source=en`、`target=ja`、`format=text`を基本とする。

**理由:** API Keyで利用でき、単純な英日テキスト翻訳を最小構成で実装できるため。

## D-007 外部翻訳Providerを初版で複数実装しない

DeepL、Azure Translator、OpenAI、Google Advanced v3はPhase 2対象外とする。

**理由:** Provider抽象化だけを保持し、初期実装・設定・テストの複雑化を避けるため。

## D-008 ログ本文だけをGoogleへ送信する

外部翻訳対象は`OriginalMessage`に由来するログ本文だけとする。

StackTrace、ファイル、行、列、Assembly Path、Shader Platform、MessageDetails、Project Root、プロジェクト名は送信しない。

**理由:** ユーザーが求めるのは説明文の日本語化であり、診断情報の翻訳は不要だから。また、不要な情報の外部送信を避けるため。

## D-009 技術識別子を不透明トークンへ置換する

ログ本文内の型名、メソッド名、Namespace、Shader Keyword、ファイルパス、GUID、バッククォート内文字列などは、Google送信前に不透明トークンへ置換する。

Google Responseで全トークンを正しく検証・復元できない場合は翻訳結果を破棄する。

**理由:** `time`、`AudioSource`、Shader Propertyなどの技術識別子が翻訳で変形されることと、ファイルパス等の外部送信を防ぐため。

## D-010 原文とStackTraceを必ず保持する

日本語訳が存在しても、原文、StackTrace、取得済み診断位置を保持する。

StackTraceは翻訳、Cache Key、Google Requestの対象にしない。

**理由:** 翻訳は補助情報であり、調査の正本はUnityまたはコンパイラの原文だから。

## D-011 Google翻訳結果をローカルCacheする

Google翻訳成功結果は、原文のSHA-256 Hashをキーとして`Library/UnityJapaneseConsoleWindow/GoogleTranslationCache.json`へ保存する。

Cacheへ原文、StackTrace、ファイルパスは保存しない。

**理由:** 同一ログへの重複通信、待ち時間、API使用量を減らし、ProjectアセットやGit差分へ混入させないため。

## D-012 API KeyをProjectへ保存しない

API KeyはEditorセッション入力またはOS環境変数`UJCW_GOOGLE_TRANSLATE_API_KEY`から取得する。

ソースコード、Assets、ScriptableObject、Project内JSON、EditorPrefs、翻訳Cacheへ保存しない。

API KeyはURL Query Parameterではなく`x-goog-api-key` Headerで送信する。

**理由:** API KeyのGit混入、URLログへの露出、Project共有時の漏洩を避けるため。

## D-013 IMGUIへ一本化する

Editor UIはIMGUIで構成し、`UnityJapaneseConsoleWindow.OnGUI`、`ConsoleWindowGui`、`ConsoleLogList`を正式UI経路とする。

UI Toolkit、UXML、USSの未使用二重実装は削除する。

**理由:** Unity標準ConsoleWindowに近いデザインと操作感へ寄せやすく、現実装も可視行だけを描画する構成を持つため。

## D-014 Unity標準Consoleのデザインへ寄せる

上部ツールバー、ログ一覧、下部詳細ペインの3領域構成とし、EditorStyles、標準Consoleアイコン、Unityテーマを優先して利用する。

過剰なカードUI、角丸、影、独自アクセントカラーを使用しない。

**理由:** Unity Editor内で違和感なく利用でき、標準Consoleからの移行コストを下げるため。

## D-015 原因推測・自動修正を対象外とする

日本語訳へ、原文から確定できない原因や修正方法を混入しない。ソースコードの自動変更も行わない。

**理由:** 翻訳機能と診断・修正機能の責務を分離するため。

## D-016 収集寿命と通信寿命をウィンドウ寿命へ合わせる

ウィンドウ有効化時に収集イベントを購読し、無効化または破棄時に解除する。

Window CloseまたはAssembly Reload時は、通信中`UnityWebRequest`をAbort・Disposeし、セッションAPI Keyを破棄する。

**理由:** mutable static状態、Singleton、常駐Controllerを導入せず、所有者と寿命を明確にするため。

## D-017 Editor専用とする

本機能とGoogle翻訳通信コードはEditor専用Assemblyへ分離し、Player、IL2CPP、実機ログ収集には使用しない。

**理由:** 目的がUnity Editor上の開発支援であり、Playerへ不要な通信依存とコードを持ち込まないため。

## D-018 標準Consoleとの状態同期を行わない

Clear、Collapse、Pause、フィルタ状態は本ウィンドウ内だけで管理する。

**理由:** 標準Console内部APIへ依存せず、動作境界を明確にするため。

## D-019 翻訳完了時は同じログ行を更新する

Google翻訳待機中は原文を表示し、翻訳完了後は同じDisplay IDの日本語表示へ更新する。

新しいログ行として追加し直さない。

**理由:** 発生回数、選択状態、Collapse状態、時系列を維持するため。

## D-020 Observationを発生回数分保持しない

同一ログは`OccurrenceCount`で回数を表し、同一内容のObservationを全件保持しない。

収集経路ごとに最も情報量の多いObservationを少数保持する。

**理由:** 同一ログ大量発生時の累積コピーとメモリ増加を防ぐため。
