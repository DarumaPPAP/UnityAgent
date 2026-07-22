# UnityJapaneseConsoleWindow 要件定義・仕様書

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.2.0`
- Status: Draft
- SpecPath: `Specs/UnityJapaneseConsoleWindow/spec.md`
- TargetPhase: Phase 2 / Google Cloud Translation連携
- LastVerified: 2026-07-23

## 1. 目的

Unity Editorで発生するログ、警告、エラー、例外、C#コンパイルメッセージ、Shaderコンパイルメッセージを収集し、原文を失わずに日本語訳を付与して閲覧できるEditor Windowを提供する。

既知のメッセージはローカル翻訳ルールで即時変換し、未登録の英語メッセージは、ユーザーが自動翻訳を有効にした場合だけGoogle Cloud Translation Basic API v2を利用して日本語へ変換する。

本機能はUnity標準Consoleを置換または改変せず、標準Consoleと並行して利用する補助Consoleとする。

## 2. 背景

Unity、URP、RenderGraph、Shader/HLSL、Burst、Jobs、Package、Asset Importなどのメッセージは英語で出力されることが多く、内容の把握に時間がかかる。

ローカル翻訳ルールだけでは、Unity本体、Package、Asset Store製品、プロジェクト固有コードが出力する未知のメッセージをすべて網羅できない。一方、ログ全体を外部サービスへ無条件に送信すると、ファイルパス、型名、メソッド名、GUID、スタックトレースなどが外部へ送信される危険がある。

このため、次のハイブリッド構成を採用する。

1. 承認済みローカル翻訳ルール
2. Google翻訳結果のローカルキャッシュ
3. Google Cloud Translation Basic v2
4. 翻訳不能時は原文表示

翻訳対象はログ本文だけとし、スタックトレースと診断位置は翻訳せず原文のまま保持する。

## 3. ゴール

1. Unity Editorで発生した対象ログを専用ウィンドウへ収集できる。
2. 登録済み翻訳ルールに一致するメッセージへ日本語訳を即時付与できる。
3. 未登録の英語メッセージをGoogle Cloud Translation Basic v2で非同期翻訳できる。
4. 同一メッセージの翻訳結果をローカルキャッシュし、2回目以降は外部通信せず表示できる。
5. 原文、スタックトレース、ファイル、行、列などの診断情報を保持できる。
6. スタックトレースを翻訳・外部送信せず、Unityから受信した文字列のまま表示できる。
7. ログ種別、カテゴリ、翻訳状態、文字列で絞り込める。
8. 同一ログを集約し、大量ログ時もEditorの操作性を維持できる。
9. 対象ファイルと行番号へ移動できる。
10. Unity標準Console、標準Logger、Playerビルドへ副作用を与えない。
11. Google API Keyをソースコード、Assets、Git管理対象へ保存しない。

## 4. 対象環境

- Unity: `6000.3`系
- Editor: Unity Editor専用
- Primary OS: Windows Editor
- Render Pipeline: 非依存
- URP: 17+環境でも動作対象
- RenderGraph: 直接依存しない
- Player: 対象外
- Namespace: `<RootNamespace>.UnityJapaneseConsoleWindow`
- UI: IMGUI
- UI基準: Unity標準ConsoleWindowに近い構成・操作感
- 表示言語: 日本語優先
- 外部翻訳: Google Cloud Translation Basic API v2
- 通信方式: HTTPS REST / `UnityWebRequest`

`Specs/ProjectProfile.md`の`RootNamespace`が未確定である場合は、実装開始前に確定する。

## 5. 用語

### 5.1 原文

Unityまたはコンパイラから受信した未変更のメッセージ文字列。

### 5.2 ログ本文

`Application.LogCallback`の`condition`、またはCompiler Messageの本文に相当する文字列。外部翻訳の対象となり得る。

### 5.3 スタックトレース

`Application.LogCallback`の`stackTrace`に相当する文字列。翻訳対象および外部送信対象外とする。

### 5.4 日本語訳

ローカル翻訳ルール、翻訳キャッシュ、Google Cloud Translationのいずれかから得られた日本語文字列。原文の代替ではなく補助表示である。

### 5.5 技術識別子

型名、メソッド名、Namespace、Shader名、Property名、Keyword、Pass名、LightMode、ファイルパス、GUID、エラーコード、数値など、翻訳によって変更してはならない文字列。

### 5.6 ローカル翻訳ルール

メッセージの完全一致、エラーコード、正規化パターンなどを条件として、日本語訳を返す決定論的な規則。

### 5.7 翻訳キャッシュ

Google Cloud Translationから取得した翻訳結果を、原文のHashをキーとしてLibrary配下へ保存するローカルデータ。

### 5.8 集約キー

同一ログを判定するために、正規化済み原文、種別、ファイル、行、カテゴリなどから生成する値。

## 6. 対象範囲

### 6.1 対象

- `Log`
- `Warning`
- `Error`
- `Assert`
- `Exception`
- C#コンパイルエラー・警告
- Unity Shader Compilerのエラー・警告
- 通常ログとして受信可能なURP、RenderGraph、Burst、Jobs、Package、Asset Import関連メッセージ
- ローカル翻訳ルール
- Google Cloud Translation Basic API v2による英語から日本語への翻訳
- Google翻訳結果のローカルキャッシュ
- 外部翻訳の有効・無効切替
- 検索、フィルタ、詳細表示、コピー、ファイル移動
- 同一ログの集約
- 翻訳状態と翻訳元の表示

### 6.2 対象外

- Unity標準Consoleの表示内容の置換
- `Debug.unityLogger`または`ILogHandler`の差し替え
- `UnityEditorInternal.LogEntries`などの内部API利用
- Reflectionによる標準Console操作
- Playerまたは実機からのリモートログ収集
- Editor.log、Player.logなどの過去ログファイルのインポート
- Google Cloud Translation Advanced API v3
- Google Translation LLM
- Google Glossary
- DeepL、Azure Translator、OpenAIなど他Provider
- スタックトレースの翻訳
- 原因や修正方法の自動生成
- ソースコードの自動修正
- 修正パッチの自動生成
- 標準ConsoleのClear、Collapse、Error Pause状態との同期
- API KeyのProject内永続保存
- 翻訳結果のクラウド同期またはチーム共有

## 7. 基本方針

### 7.1 標準Consoleとの関係

UnityJapaneseConsoleWindowは標準Consoleから独立した補助ウィンドウとする。標準Consoleへ出力される原文を変更、削除、抑止しない。

### 7.2 公開API限定

ログ収集、診断情報取得、外部通信にはUnity 6000.3で公開されているAPIだけを使用する。内部API、非公開型、Reflectionに依存しない。

### 7.3 原文優先

日本語訳が存在する場合も原文を必ず保持する。翻訳結果だけを保持して原文を失わせてはならない。

### 7.4 翻訳優先順位

翻訳は次の固定順序で解決する。

1. 原文完全一致ルール
2. コンパイラエラーコードルール
3. 正規化済みパターンルール
4. Google翻訳キャッシュ
5. Google Cloud Translation Basic v2
6. 原文表示

ルール登録順やUI設定によって優先順位を変更してはならない。

### 7.5 外部翻訳は明示的なOpt-in

Google翻訳は初期状態で無効とする。ユーザーが明示的に有効化した場合だけ未知ログを外部送信する。

手動の「このログを翻訳」は、ユーザーの明示操作として自動翻訳OFF時でも実行できる。

### 7.6 翻訳対象の分離

外部翻訳対象はログ本文のみとする。

以下はGoogle Cloud Translationへ送信しない。

- スタックトレース
- ファイルパス
- 行番号・列番号
- Assembly Path
- Shader Platform
- MessageDetails
- Unityプロジェクト名
- Project Root
- 収集経路

ログ本文内にファイルパスや技術識別子が含まれる場合は、送信前に不透明トークンへ置換する。

### 7.7 識別子保護

翻訳前に技術識別子を抽出・保護し、日本語訳へ復元する。必要なトークンを安全に復元できない場合は翻訳結果を採用しない。

### 7.8 所有権と寿命

ログ収集状態、表示データ、翻訳Queue、翻訳Cache、非秘密設定、通信中RequestはUnityJapaneseConsoleWindowが所有する。

ウィンドウを開いた時点で購読を開始し、閉じた時点で解除・破棄する。ウィンドウが閉じている間のログは収集対象外とする。

### 7.9 IMGUI

UIはIMGUIへ一本化する。UI Toolkit、UXML、USSの二重実装を残さない。

Unity標準ConsoleWindowに近い次の構成とする。

1. 上部ツールバー
2. ログ一覧
3. 下部詳細ペイン

## 8. ログ収集仕様

### FR-001 ウィンドウ起動

メニューから`UnityJapaneseConsoleWindow`を開けること。

ウィンドウは同一Editor内で原則1インスタンスとする。

### FR-002 通常ログ収集

`Application.logMessageReceivedThreaded`を利用して、メインスレッドおよび別スレッドからUnity内部ログシステムへ渡されたメッセージを受信できること。

受信コールバックでは以下だけを行うこと。

- 受信文字列の保持
- ログ種別の保持
- 受信時刻の保持
- スレッドセーフな待機列への追加

受信コールバック内では以下を行わないこと。

- Unity Editor APIアクセス
- UI更新
- 翻訳ルール評価
- 翻訳Cache検索
- Google API通信
- JSON生成
- 正規表現処理
- ファイルI/O
- `Debug.Log`系の再出力

### FR-003 C#コンパイルメッセージ収集

`CompilationPipeline.assemblyCompilationFinished`から、各Assemblyの`CompilerMessage`を受信できること。

以下を保持すること。

- Assembly出力パス
- メッセージ種別
- 原文
- ファイル
- 行
- 列

### FR-004 Shaderコンパイルメッセージ

通常ログとして受信したShader関連メッセージを分類できること。

対象Shaderを公開APIで解決できる場合は、`ShaderUtil.GetShaderMessages`と`ShaderMessage`を用いて以下を補完できること。

- ファイル
- 行
- Severity
- Platform
- Message
- MessageDetails

Shaderを解決できない場合は、通常ログの原文を保持して表示を継続すること。

### FR-005 メインスレッド取り込み

待機列に追加されたログはEditorのメインスレッド側で取り込み、分類、正規化、ローカル翻訳、Cache検索、外部翻訳候補登録、集約、UI更新を行うこと。

1フレーム内で無制限に処理せず、処理件数または処理時間に上限を持つこと。

### FR-006 再帰ログ防止

本ツール内部の処理から`Debug.Log`、`Debug.LogWarning`、`Debug.LogError`を使用して通常運用ログを出力しないこと。

Google通信エラーをUnity Consoleへ再出力してはならない。内部状態は本ウィンドウのステータス表示へ出すこと。

## 9. ログモデル仕様

### FR-007 必須保持項目

1件の表示ログは、取得できる範囲で以下を保持すること。

- 一意な表示ID
- 初回発生時刻
- 最終発生時刻
- 発生回数
- LogType
- カテゴリ
- 原文
- 日本語訳
- 翻訳状態
- 翻訳元
- 翻訳ルールID
- Source Message Hash
- スタックトレース
- ファイル
- 行
- 列
- Assembly
- Shader Platform
- MessageDetails
- 集約キー
- 外部翻訳失敗理由

### FR-008 翻訳状態

最低限以下を区別できること。

- `UNTRANSLATED`
- `EXACT_MATCH`
- `ERROR_CODE_MATCH`
- `PATTERN_MATCH`
- `CACHE_MATCH`
- `GOOGLE_PENDING`
- `GOOGLE_TRANSLATED`
- `GOOGLE_FAILED`
- `TRANSLATION_FAILED`

`TRANSLATION_FAILED`はローカル翻訳または識別子保護失敗、`GOOGLE_FAILED`は通信・認証・Response検証失敗として区別する。

### FR-009 翻訳元

最低限以下を区別できること。

- Local Rule
- Google Cache
- Google Cloud Translation
- None

### FR-010 カテゴリ

最低限以下のカテゴリを持つこと。

- General
- CSharpCompiler
- ShaderCompiler
- RenderGraph
- URP
- Burst
- Jobs
- Package
- AssetImport
- Unknown

分類不能なメッセージは`Unknown`とし、推測で別カテゴリへ断定しないこと。

## 10. ローカル翻訳仕様

### FR-011 ローカル翻訳パイプライン

ローカル翻訳は以下の優先順で評価すること。

1. 原文完全一致
2. コンパイラエラーコード一致
3. 正規化済みパターン一致
4. 未翻訳

### FR-012 ローカル識別子保護

最低限以下を保護対象とすること。

- `'...'`、`"..."`、バッククォート内の識別子
- C#エラーコード
- Unity Asset相対パス
- 絶対ファイルパス
- Namespace、型名、メソッド名として認識できるトークン
- Shader Keyword
- Shader Property
- Pass名、LightMode
- GUID
- 行番号、列番号、数値

### FR-013 日本語訳の責務

日本語訳は原文の意味だけを表す。

原文から確定できない原因、修正方法、性能評価、推奨コードを混入してはならない。

### FR-014 ルールの追跡可能性

適用した翻訳ルールIDを詳細画面で確認できること。

翻訳ルールはVersion Controlで差分確認できる形式とし、ルール変更で既存メッセージの意味が変わる場合に追跡可能であること。

既存実装に合わせ、初期保存形式はC#定義とする。

## 11. Google Cloud Translation仕様

### FR-015 Google Translation Provider

初期ProviderはGoogle Cloud Translation Basic API v2だけとする。

HTTP Endpoint:

```text
POST https://translation.googleapis.com/language/translate/v2
```

RequestはJSON形式とし、最低限以下を指定する。

```json
{
  "q": ["translation target"],
  "source": "en",
  "target": "ja",
  "format": "text"
}
```

API Keyは`x-goog-api-key` HTTP Headerで送信する。

### FR-016 自動翻訳対象判定

次をすべて満たすログだけを自動翻訳候補とする。

- ローカル翻訳結果が`UNTRANSLATED`
- 自動翻訳が有効
- API Keyが利用可能
- 原文が空でない
- 原文に英字を含む
- 原文が日本語中心ではない
- 同じSource Message HashがCache、待機Queue、通信中Requestに存在しない
- Sanitizerが送信可能と判定した

以下は自動送信しない。

- StackTraceだけの文字列
- ファイルパスだけの文字列
- GUIDだけの文字列
- 数値だけの文字列
- 空白だけの文字列
- 既に日本語中心の文字列
- 8KiBを超える単一ログ本文

### FR-017 外部送信用Sanitize

Googleへ送信する前に、最低限以下を不透明トークンへ置換する。

- バッククォート内文字列
- 引用符内識別子
- C#エラーコード
- 型名
- Namespace
- メソッド名
- Shader名
- Shader Property
- Shader Keyword
- Pass名
- LightMode
- Unity Asset相対パス
- 絶対パス
- GUID
- URL
- メールアドレス
- IPアドレス
- Instance ID

トークン形式は翻訳対象言語に依存しないASCII文字列とする。

例:

```text
__UJCW_TOKEN_0000__
```

### FR-018 Google Response検証

Google Responseから`data.translations[]`を取得する。

採用前に以下を検証する。

- HTTP通信成功
- JSON解析成功
- Request件数とResponse件数が一致
- `translatedText`が空でない
- 必須トークンがすべて存在する
- 必須トークンが重複または改変されていない
- 未知トークンが追加されていない
- 復元後文字列が空でない

検証に失敗した場合は翻訳結果を採用せず、原文表示を継続する。

### FR-019 非同期表示更新

Google翻訳待機中もログを即座に一覧へ表示する。

待機中:

```text
1行目: 英語原文
2行目: StackTrace先頭行
状態: Google翻訳待機中
```

翻訳完了後:

```text
1行目: 日本語訳
2行目: StackTrace先頭行
状態: Google翻訳済み
```

翻訳完了時に新しい行を追加せず、同じ表示IDを維持して更新する。

### FR-020 StackTrace無加工

StackTraceは次の処理対象外とする。

- Google翻訳
- Google API Request
- Google Cache Key
- 外部送信用Sanitize

一覧と詳細では、Unityから受信したStackTraceを原文のまま表示する。

### FR-021 Request重複防止

同じSource Message Hashを持つログが複数回発生しても、Google API Requestは1回だけとする。

Source Message Hashには最低限以下を含める。

```text
SHA-256(
    OriginalMessage
    + SourceLanguage
    + TargetLanguage
    + SanitizerVersion
    + ProviderOptionsVersion
)
```

発生回数は既存の`OccurrenceCount`へ集約する。

### FR-022 Batch送信

複数の翻訳待機メッセージを1Requestへまとめられること。

初期値:

- 最大16メッセージ
- 最大32KiBのJSON Payload
- 最大同時Request数1
- 最大待機時間100ms

Google Basic v2の`q`配列上限128件より小さい安全側の値を採用する。

### FR-023 Retry

以下の場合だけ再試行する。

- Connection Error
- HTTP 429
- HTTP 500～599

再試行間隔:

```text
1回目: 1秒
2回目: 2秒
3回目: 4秒
```

最大3回とする。

以下は再試行しない。

- 400: Request不正
- 401 / 403: 認証・権限エラー
- JSON解析失敗
- トークン復元失敗

### FR-024 通信失敗

通信失敗時もログを削除しない。

英語原文とStackTraceを表示し、詳細ペインへ以下を表示する。

- 翻訳状態
- HTTP Status
- 失敗理由
- Retry回数
- 最終試行時刻

### FR-025 手動翻訳

詳細ペインまたは右クリックメニューから以下を実行できる。

- このログをGoogle翻訳
- Google翻訳を再試行
- この翻訳Cacheを削除
- 原文表示
- 日本語表示

自動翻訳がOFFでも、ユーザーの明示操作ならGoogle翻訳を実行できる。

## 12. 翻訳Cache仕様

### FR-026 Cache検索

ローカル翻訳ルールへ一致しなかった場合、Google通信前にCacheを検索する。

Cache Hit時は通信せず`CACHE_MATCH`として日本語訳を表示する。

### FR-027 Cache保存先

Cacheは次へ保存する。

```text
Library/UnityJapaneseConsoleWindow/GoogleTranslationCache.json
```

Assets、Packages、ProjectSettings、Git管理対象へ保存してはならない。

### FR-028 Cache Entry

最低限以下を保持する。

- Source Message Hash
- Japanese Translation
- Source Language
- Target Language
- Sanitizer Version
- Provider Options Version
- CreatedAtUtc
- LastUsedAtUtc

原文、StackTrace、ファイルパスはCacheへ保存しない。

### FR-029 Cache上限

最大5,000件とする。

上限超過時は`LastUsedAtUtc`が古いEntryから削除する。

Cache書き込みは翻訳完了ごとに同期実行せず、Dirty状態から一定時間後にまとめて保存する。

### FR-030 Cache無効化

以下が変更された場合は旧Cacheを利用しない。

- Source Language
- Target Language
- Sanitizer Version
- Provider Options Version

## 13. API Key・設定仕様

### FR-031 API Key解決

API Keyは次の優先順で取得する。

1. Editorセッション中だけ保持する入力値
2. OS環境変数`UJCW_GOOGLE_TRANSLATE_API_KEY`

以下への保存は禁止する。

- C#ソースコード
- `Assets/`
- ScriptableObject
- Project内JSON
- Git管理対象
- 翻訳Cache

API Keyをログ、例外、ステータス、Tooltipへ表示してはならない。

### FR-032 非秘密設定

以下はEditorPrefsへ保存可能とする。

- 自動翻訳ON/OFF
- Cache容量
- Batch最大件数
- ツールバー表示設定

API KeyはEditorPrefsへ保存しない。

### FR-033 API Key制限

仕様上、Google Cloud側で対象API KeyをCloud Translation APIだけに制限する運用を推奨する。

アプリケーション制限を適用できる運用環境では併用する。

## 14. 集約・更新仕様

### FR-034 同一ログ集約

同一と判定したログは1行へ集約し、発生回数、初回発生時刻、最終発生時刻を更新すること。

集約キーには最低限以下を含めること。

- 正規化済み原文
- LogType
- カテゴリ
- ファイル
- 行

C#コンパイルイベントと通常ログイベントの両方で同一メッセージを取得した場合は、重複表示を抑止し、構造化情報が多い側へ統合すること。

### FR-035 Observation上限

同一ログが大量発生しても、同一内容のObservationを発生回数分保持しない。

収集経路ごとに最も情報量の多いObservationを保持し、Observation数へ明示的な上限を設ける。

### FR-036 翻訳結果適用

Google翻訳完了時は、同じSource Message Hashを持つCollapsed ViewとIndividual Viewの対象レコードへ結果を適用する。

以下を維持する。

- Display ID
- OccurrenceCount
- FirstOccurredAt
- LastOccurredAt
- Observations
- Aggregation Key

更新対象:

- Japanese Translation
- Translation State
- Translation Source
- Failure Reason
- Search Document

### FR-037 Collapse切替

ユーザーは集約表示と個別表示を切り替えられること。

個別表示でも保持上限を超えて無制限に増加させないこと。

### FR-038 保持上限

初期値として最大10,000件の表示レコードを保持すること。

上限到達時は最も古いレコードから削除し、Editorのメモリを無制限に増加させないこと。

## 15. UI仕様

### FR-039 基本レイアウト

IMGUIで以下の構成を持つこと。

1. 上部ツールバー
2. ログ一覧
3. 下部詳細ペイン

ログ一覧と詳細はリサイズ可能な分割表示とする。

### FR-040 上部ツールバー

Unity標準Consoleに近い配置とする。

左側:

- Clear
- Collapse
- Pause

中央:

- カテゴリ
- 翻訳状態
- Google翻訳メニュー

右側:

- 検索
- Log表示切替
- Warning表示切替
- Error / Assert / Exception表示切替

### FR-041 Google翻訳メニュー

最低限以下を提供する。

- 未知ログを自動Google翻訳
- API Keyセッション入力
- API Key取得元表示
- Google接続テスト
- Cache件数
- Cacheをクリア

API Key入力はPassword Fieldを使用し、現在値を再表示しない。

### FR-042 ログ一覧

翻訳済みログ:

```text
1行目: 日本語訳
2行目: StackTrace先頭行
```

未翻訳・待機中・失敗ログ:

```text
1行目: 英語原文
2行目: StackTrace先頭行
```

StackTraceが存在しない場合は、2行目へファイル位置、発生時刻、収集経路の順で利用可能な情報を表示する。

一覧には最低限以下を表示する。

- 種別アイコン
- 発生回数
- 主表示
- 副表示
- 翻訳待機・失敗状態

全件を描画せず、スクロール位置から可視行だけを描画すること。

### FR-043 詳細表示

選択ログについて最低限以下を表示する。

1. 日本語訳
2. 原文
3. スタックトレース
4. ファイル・行・列
5. Assembly
6. Shader Platform
7. MessageDetails
8. 初回発生時刻
9. 最終発生時刻
10. 発生回数
11. 翻訳状態
12. 翻訳元
13. 翻訳ルールID
14. Google通信失敗理由

取得できない項目は非表示または`取得不可`とし、推測値を表示しないこと。

### FR-044 検索

検索は最低限以下を対象とする。

- 原文
- 日本語訳
- ファイル
- カテゴリ
- エラーコード
- スタックトレース

### FR-045 コピー

以下を提供する。

- 表示内容をコピー: 日本語訳または原文 + StackTrace
- 原文をコピー: 原文 + StackTrace
- 日本語訳をコピー
- StackTraceをコピー
- 詳細全体をコピー

### FR-046 ファイル移動

ファイルと行番号を解決できるログは、一覧のダブルクリックまたは詳細ボタンから外部コードエディタの対象行へ移動できること。

### FR-047 Pause

Pause中は受信ログを失わず待機列または保留領域へ保持し、一覧の反映だけを停止すること。

Pause中は新しいGoogle翻訳Requestを開始しない。既に通信中のRequestは完了可能とするが、表示適用はResume後に行う。

### FR-048 Clear

Clearは本ウィンドウが保持するログと待機中翻訳Queueを消去すること。

通信中RequestはAbort・Disposeする。

Google翻訳CacheはClearでは削除しない。

### FR-049 外観

Unity標準Consoleに近いEditorStyles、アイコン、選択色、行高を使用する。

過剰なカードUI、角丸、影、独自アクセントカラーを使用しない。

Dark ThemeとLight Themeの両方で判読可能であること。

## 16. Editorライフサイクル仕様

### FR-050 購読管理

ウィンドウ有効化時に必要なイベントを1回だけ購読し、無効化または破棄時に必ず解除すること。

Domain Reload、Assembly Reload、ウィンドウ再生成後に重複購読を発生させないこと。

### FR-051 通信破棄

Window CloseまたはAssembly Reload前に以下を行う。

- 新規Google翻訳受付停止
- 通信中UnityWebRequestをAbort
- UnityWebRequestをDispose
- Dirty Cacheを保存
- セッションAPI Keyを破棄
- update購読解除

### FR-052 Hot Reload

Domain Reloadを跨いだログ履歴と通信Requestの保持は必須要件としない。

Reload後に通信を自動再開しない。

### FR-053 Editor専用分離

本機能のコードとアセットはEditor専用Assemblyへ分離され、Playerビルドへ含まれないこと。

## 17. 非機能要件

### NFR-001 スレッド安全性

`Application.logMessageReceivedThreaded`のコールバックは並列呼び出しを前提とし、共有状態への非同期アクセスで競合、破損、例外を発生させないこと。

### NFR-002 標準機能非侵襲

標準Console、`Debug.unityLogger`、既存`ILogHandler`、既存ログフィルタへ変更を加えないこと。

### NFR-003 公開API互換性

Unity 6000.3で公開されているAPIだけを使用すること。内部API、Reflection、非公開フィールドへの依存を0件とする。

### NFR-004 Editor応答性

Google通信完了を同期的に待機してEditorをブロックしない。

ログ受信コールバック内にUI更新、翻訳、正規表現、JSON生成、ファイルI/O、Google通信が存在しないことをコード監査で確認する。

メインスレッド側は1フレームの処理時間上限を持つこと。

### NFR-005 メモリ上限

保持件数上限を超えてログモデル、Observation、翻訳Queue、翻訳Cacheが無制限に増加しないこと。

### NFR-006 データ完全性

日本語訳生成の成否にかかわらず、受信した原文、StackTrace、診断位置を変更しないこと。

### NFR-007 オフライン継続

ネットワーク接続、API Key、Google Cloud障害の有無にかかわらず、ローカル翻訳、原文表示、検索、Collapse、ファイルジャンプを継続できること。

### NFR-008 セキュリティ

API Keyをコード、Projectファイル、Git、ログへ含めない。

StackTraceと診断位置をGoogleへ送信しない。

API KeyはURL Query Parameterではなく`x-goog-api-key` Headerで送信する。

### NFR-009 Fail Closed

識別子復元、Response件数、JSON解析、通信結果の検証に失敗した場合、Google翻訳結果を採用しない。

### NFR-010 通信量

同じSource Message Hashを同一セッションで複数回送信しない。

Cache Hit時はGoogle通信を行わない。

### NFR-011 保守性

ログ収集、分類、正規化、ローカル翻訳、外部送信用Sanitize、Google Provider、翻訳Queue、Cache、翻訳結果適用、UI表示を責務単位で分離すること。

`Manager`、`Controller`、`Util`、`Common`、`Helper`という曖昧な型を導入しないこと。

### NFR-012 命名・構成

- Namespace: `<RootNamespace>.UnityJapaneseConsoleWindow`
- private field: `_camelCase`
- public API/type/member: `PascalCase`
- enum: `E_UPPER_SNAKE_CASE`
- struct: `S_UPPER_SNAKE_CASE`
- const: `SCREAMING_SNAKE_CASE`
- コメント: 日本語で理由、制約、意図を記述

### NFR-013 テスト可能性

Google APIへ実接続しないFake Providerを使用し、外部送信用Sanitize、Queue、Retry、Cache、結果適用をEditMode Testできること。

### NFR-014 正確な表示

翻訳できない内容を翻訳済みとして扱わないこと。原因不明の内容を断定しないこと。取得できないPlatform、Assembly、行番号などを推測しないこと。

## 18. 基本設計

### 18.1 TranslationResolutionPipeline

責務:

- ローカル翻訳評価
- Cache検索
- Google翻訳対象判定
- Google翻訳Queue登録
- 初期翻訳状態返却

通信処理とUI描画は持たない。

### 18.2 ExternalTranslationSanitizer

責務:

- 機密文字列・技術識別子抽出
- 不透明トークン置換
- 復元Map生成
- Responseトークン検証
- 日本語結果復元

### 18.3 GoogleTranslationProvider

責務:

- Google Basic v2 Request DTO生成
- `UnityWebRequest`生成
- `x-goog-api-key` Header設定
- Response DTO解析
- HTTP・JSONエラー分類

ログモデルとUIへ直接依存しない。

### 18.4 GoogleTranslationQueue

責務:

- Source Message Hashによる重複排除
- Batch形成
- 同時Request数制御
- Retry待機
- Request開始・完了監視
- 完了結果Queue出力

### 18.5 TranslationCacheStore

責務:

- Cache読込
- Cache検索
- Cache追加
- LRU削除
- Dirty管理
- 遅延保存
- Version不一致Cache無効化

### 18.6 TranslationSettingsStore

責務:

- 非秘密設定のEditorPrefs読込・保存
- 初期値管理

API Keyを扱わない。

### 18.7 TranslationSecretResolver

責務:

- セッションAPI Key保持
- 環境変数API Key取得
- API Key利用可否判定

### 18.8 TranslationResultApplier

責務:

- Google翻訳完了結果をLogAggregationStoreへ適用
- Collapsed / Individual View更新
- Display ID維持
- Search Document再構築
- Store Mutation発行

### 18.9 既存クラス変更

#### EditorLogPump

`TranslationRuleEvaluator`単独ではなく`TranslationResolutionPipeline`を利用する。

#### LogRecord

以下を追加する。

- Translation Source
- Source Message Hash
- Translation Failure Reason

#### LogAggregationStore

以下を追加する。

- `ApplyTranslationResult`
- Observation重複抑止
- Observation上限

#### UnityJapaneseConsoleWindow

以下を生成・所有・破棄する。

- TranslationResolutionPipeline
- ExternalTranslationSanitizer
- GoogleTranslationProvider
- GoogleTranslationQueue
- TranslationCacheStore
- TranslationSettingsStore
- TranslationSecretResolver
- TranslationResultApplier

#### ConsoleWindowGui

以下を追加する。

- Google翻訳メニュー
- API Keyセッション入力
- 接続テスト
- 翻訳待機・失敗状態
- 手動翻訳
- Cache操作

## 19. 受け入れ条件

### AC-001 ウィンドウ表示

**検証:** メニューからウィンドウを開く。

**合格:** Unity標準Consoleに近いIMGUIの一覧・詳細・ツールバーが表示され、Consoleエラーを発生させない。

### AC-002 通常ログ受信

**検証:** `Log`、`Warning`、`Error`、`Assert`、`Exception`を各1件発生させる。

**合格:** 全種別が一覧へ表示され、原文と種別が一致する。

### AC-003 別スレッドログ受信

**検証:** 別スレッドからログを発生させる。

**合格:** 競合例外、Unity APIスレッド例外、欠損によるウィンドウ停止が発生しない。

### AC-004 ローカル翻訳優先

**検証:** 登録済みルールに一致するログを、自動Google翻訳ONで発生させる。

**合格:** Google通信0回でローカル翻訳が表示される。

### AC-005 Cache優先

**検証:** 一度Google翻訳した未知ログを再度発生させる。

**合格:** 2回目はGoogle通信0回でCache結果が即時表示される。

### AC-006 Google翻訳

**検証:** API Key設定済み、自動翻訳ONで未知の英語ログを発生させる。

**合格:** 英語原文が先に表示され、通信完了後に同じ表示IDの日本語表示へ更新される。

### AC-007 StackTrace非送信

**検証:** 次のAudioSource警告を発生させる。

```text
Attempting to set `time` on an audio source that has a resource assigned that is not a clip is ignored!
UnityEngine.AudioSource:set_time (single)
```

**合格:** Google Request PayloadへStackTraceが含まれず、画面上ではStackTraceが原文のまま表示される。

### AC-008 期待表示

**合格例:**

```text
クリップ以外のリソースが割り当てられているAudioSourceに `time` を設定しようとすると、この操作は無視されます。
UnityEngine.AudioSource:set_time (single)
```

Googleの実際の翻訳文が上記と完全一致することは必須としない。技術識別子とStackTraceが保持され、日本語として意味が成立することを合格条件とする。

### AC-009 技術識別子保持

**検証:** `time`、型名、メソッド名、Shader Keyword、ファイルパスを含むメッセージを翻訳する。

**合格:** Requestでは保護され、表示時に原文と同一文字列へ復元される。

### AC-010 トークン改変拒否

**検証:** Fake Providerがトークンを削除または改変したResponseを返す。

**合格:** 翻訳結果を破棄し、原文表示を維持し、`GOOGLE_FAILED`となる。

### AC-011 同一ログ重複防止

**検証:** 同じ未知ログを100回発生させる。

**合格:** Google Requestは1件、OccurrenceCountは100、翻訳完了後も1行表示となる。

### AC-012 自動翻訳OFF

**検証:** 自動翻訳OFFで未知ログを発生させる。

**合格:** Google通信0回で原文表示となる。

### AC-013 API Key未設定

**検証:** 自動翻訳ON、API Keyなしで未知ログを発生させる。

**合格:** Google通信0回で原文表示となり、API Key未設定状態が表示される。

### AC-014 通信失敗

**検証:** Connection ErrorまたはFake Providerで500を返す。

**合格:** 最大3回Retry後、原文を保持し、Editor操作を継続できる。

### AC-015 認証失敗

**検証:** Fake Providerで401または403を返す。

**合格:** Retryせず、原文を保持し、認証エラーを表示する。

### AC-016 C#重複統合

**検証:** 同一C#コンパイルメッセージを通常ログ経路とCompilationPipeline経路で受信する。

**合格:** 二重表示されず、ファイル・行・列を持つ構造化レコードへ統合される。

### AC-017 Observation上限

**検証:** 同一ログを10,000回投入する。

**合格:** OccurrenceCountは10,000となり、Observation数は設定上限以内で、過去全Observationを毎回複製しない。

### AC-018 PauseとClear

**検証:** Pause中にログを発生させ、Resume後に反映する。通信中にClearする。

**合格:** Pause中の一覧更新が止まり、Resume後に反映される。Clear時に通信が安全にAbortされる。

### AC-019 Domain Reload

**検証:** Google通信中にAssembly Reloadを発生させる。

**合格:** RequestをAbort・Disposeし、重複購読、例外、API Key漏洩が発生しない。

### AC-020 Player分離

**検証:** Player向けAssembly定義とビルド対象を確認する。

**合格:** 本機能とGoogle通信コードがPlayerコンパイル対象へ含まれない。

### AC-021 内部API不使用

**検証:** コード検索と参照Assembly監査を行う。

**合格:** `UnityEditorInternal.LogEntries`、標準Console内部型、Reflectionによる非公開メンバーアクセスが0件である。

## 20. テスト方針

### 20.1 EditMode Test

- ローカルRuleがCacheより優先される
- CacheがGoogle通信より優先される
- 自動翻訳OFFではRequestを作らない
- API KeyなしではRequestを作らない
- 同一Source Message Hashを重複登録しない
- Batch最大件数
- Batch最大Byte数
- トークン抽出
- トークン復元
- トークン不足
- トークン重複
- StackTraceがPayloadへ含まれない
- ファイルパスがPayloadへ含まれない
- Cache Version不一致
- Cache LRU削除
- Retry対象判定
- 429 / 500指数バックオフ
- 401 / 403非Retry
- Response件数不一致
- Store更新後もDisplay ID維持
- Search Document更新
- Domain Reload前Dispose
- 同一ログ10,000件のObservation上限

自動テストでは実際のGoogle APIへ接続しない。Fake Providerを使用する。

### 20.2 Unity Editor手動テスト

- 有効なGoogle Cloud Translation API Key
- 無効なAPI Key
- ネットワーク切断
- AudioSource警告
- C#コンパイルエラー
- Shaderコンパイルエラー
- 同一ログ大量発生
- Pause中の翻訳
- Clear中の通信完了
- Window Close中の通信
- Dark Theme
- Light Theme

## 21. 実装順序

1. Observation重複保持・C#重複統合修正
2. IMGUI一本化とUnity標準Consoleデザイン調整
3. 翻訳状態・翻訳元・Source Message Hash拡張
4. ExternalTranslationSanitizer
5. TranslationCacheStore
6. TranslationSettingsStore / TranslationSecretResolver
7. GoogleTranslationProviderとFake Provider
8. GoogleTranslationQueue / Batch / Retry
9. TranslationResultApplier / Store更新
10. IMGUI Google翻訳設定・手動翻訳
11. EditMode Test
12. Unity Editor手動受け入れテスト

## 22. 未決定事項

### UD-001 RootNamespace

`Specs/ProjectProfile.md`が未確定の場合は、実装前にRootNamespaceを確定する。

### UD-002 1フレーム処理上限

ログ処理と翻訳結果適用の最大件数または最大処理時間を、基準PCと計測方法を定義して確定する。

### UD-003 Cache保存頻度

Dirty Cacheの保存待機時間は初期案2秒とし、Editor I/O計測後に確定する。

### UD-004 Google API利用上限

Google Cloud側のQuota、Budget Alert、API Key制限は運用設定であり、本ツール内では設定しない。導入手順書で定義する。

## 23. 実装前ゲート

1. `UD-001` RootNamespace確定
2. Observation増殖問題修正方針確定
3. C#コンパイル重複統合方針確定
4. `plan.md`作成
5. `tasks.md`作成
6. Fake Providerテスト方針確定
7. Google Cloud Project・API Key準備手順作成
8. 大量ログ計測条件確定

## 24. 参考資料

- Unity 6 `Application.logMessageReceivedThreaded`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Application-logMessageReceivedThreaded.html
- Unity 6 `CompilationPipeline.assemblyCompilationFinished`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Compilation.CompilationPipeline-assemblyCompilationFinished.html
- Unity 6 `ShaderUtil.GetShaderMessages`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ShaderUtil.GetShaderMessages.html
- Unity 6 `UnityWebRequest.Post`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Networking.UnityWebRequest.Post.html
- Unity 6 `UnityWebRequest.Result`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Networking.UnityWebRequest.Result.html
- Google Cloud Translation Basic v2 `translate`
  - https://docs.cloud.google.com/translate/docs/reference/rest/v2/translate
- Google Cloud Translation Authentication
  - https://docs.cloud.google.com/translate/docs/authentication
- Google Cloud API Key Best Practices
  - https://docs.cloud.google.com/docs/authentication/api-keys-best-practices
