# UnityJapaneseConsoleWindow 要件定義・仕様書

- FeatureName: `UnityJapaneseConsoleWindow`
- DocumentVersion: `0.1.0`
- Status: Draft
- SpecPath: `Specs/UnityJapaneseConsoleWindow/spec.md`
- TargetPhase: 要件定義・仕様策定のみ
- LastVerified: 2026-07-22

## 1. 目的

Unity Editorで発生するログ、警告、エラー、例外、C#コンパイルメッセージ、Shaderコンパイルメッセージを収集し、原文を失わずに日本語の要約を付与して閲覧できるEditor Windowを提供する。

本機能はUnity標準Consoleを置換または改変せず、標準Consoleと並行して利用する補助Consoleとする。

## 2. 背景

Unity、URP、RenderGraph、Shader/HLSL、Burst、Jobs、Package、Asset Importなどのメッセージは英語で出力されることが多く、内容の把握に時間がかかる。

単純な全文翻訳では、型名、メソッド名、Shader Keyword、ファイルパス、エラーコードなどの技術識別子まで変形される危険がある。また、Unity標準Consoleの内部状態へReflectionで依存すると、Unity更新による破損リスクが高い。

このため、公開APIで取得できる情報だけを使用し、識別子を保護した決定論的な翻訳と、原文・スタックトレース・発生位置の保持を両立する。

## 3. ゴール

1. Unity Editorで発生した対象ログを専用ウィンドウへ収集できる。
2. 登録済み翻訳ルールに一致するメッセージへ日本語要約を付与できる。
3. 原文、スタックトレース、ファイル、行、列などの診断情報を保持できる。
4. ログ種別、カテゴリ、翻訳状態、文字列で絞り込める。
5. 同一ログを集約し、大量ログ時もEditorの操作性を維持できる。
6. 対象ファイルと行番号へ移動できる。
7. Unity標準Console、標準Logger、Playerビルドへ副作用を与えない。

## 4. 対象環境

- Unity: `6000.3`系
- Editor: Unity Editor専用
- Primary OS: Windows Editor
- Render Pipeline: 非依存
- URP: 17+環境でも動作対象
- RenderGraph: 直接依存しない
- Player: 対象外
- Namespace: `<RootNamespace>.UnityJapaneseConsoleWindow`
- UI: UI Toolkit
- 表示言語: 日本語優先
- 外観: 黒基調、白文字を基本

`Specs/ProjectProfile.md`の`RootNamespace`が未確定であるため、実装開始前に確定が必要である。

## 5. 用語

### 5.1 原文

Unityまたはコンパイラから受信した未変更のメッセージ文字列。

### 5.2 日本語要約

翻訳ルールにより生成される、日本語での短い意味説明。原文の代替ではなく補助情報である。

### 5.3 技術識別子

型名、メソッド名、Namespace、Shader名、Property名、Keyword、Pass名、LightMode、ファイルパス、GUID、エラーコード、数値など、翻訳によって変更してはならない文字列。

### 5.4 翻訳ルール

メッセージの完全一致、エラーコード、正規化パターンなどを条件として、日本語要約と任意の補足を返す決定論的な規則。

### 5.5 集約キー

同一ログを判定するために、正規化済みメッセージ、種別、ファイル、行、カテゴリなどから生成する値。

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
- 検索、フィルタ、詳細表示、コピー、ファイル移動
- 同一ログの集約
- 翻訳ルールの適用状況表示

### 6.2 対象外

- Unity標準Consoleの表示内容の置換
- `Debug.unityLogger`または`ILogHandler`の差し替え
- `UnityEditorInternal.LogEntries`などの内部API利用
- Reflectionによる標準Console操作
- Playerまたは実機からのリモートログ収集
- Editor.log、Player.logなどの過去ログファイルのインポート
- 外部AI、外部翻訳API、ネットワーク通信
- 未登録メッセージの自動機械翻訳
- ソースコードの自動修正
- 修正パッチの自動生成
- 原因や修正方法の推測生成
- 標準ConsoleのClear、Collapse、Error Pause状態との同期

## 7. 基本方針

### 7.1 標準Consoleとの関係

UnityJapaneseConsoleWindowは標準Consoleから独立した補助ウィンドウとする。標準Consoleへ出力される原文を変更、削除、抑止しない。

### 7.2 公開API限定

ログ収集と診断情報取得にはUnity 6で公開されているAPIだけを使用する。内部API、非公開型、Reflectionに依存しない。

### 7.3 原文優先

翻訳結果が存在する場合も原文を必ず保持する。翻訳結果だけを表示して原文を失わせてはならない。

### 7.4 決定論的翻訳

初版はローカルの翻訳ルールだけを使用する。同一入力と同一ルールバージョンからは同一結果を返す。

### 7.5 識別子保護

翻訳前に技術識別子を抽出・保護し、日本語要約へ復元する。保護に失敗する可能性がある場合は、無理に翻訳せず未翻訳として扱う。

### 7.6 所有権と寿命

ログ収集状態、表示データ、フィルタ状態はUnityJapaneseConsoleWindowが所有する。ウィンドウを開いた時点で購読を開始し、閉じた時点で解除する。

ウィンドウが閉じている間のログは収集対象外とする。

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
- 翻訳処理
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

待機列に追加されたログはEditorのメインスレッド側で取り込み、分類、正規化、翻訳、集約、UI更新を行うこと。

1フレーム内で無制限に処理せず、処理件数または処理時間に上限を持つこと。

### FR-006 再帰ログ防止

本ツール内部の処理から`Debug.Log`、`Debug.LogWarning`、`Debug.LogError`を使用して通常運用ログを出力しないこと。

内部例外を通知する必要がある場合は、再帰を発生させない経路で状態表示すること。

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
- 日本語要約
- 翻訳状態
- 翻訳ルールID
- スタックトレース
- ファイル
- 行
- 列
- Assembly
- Shader Platform
- MessageDetails
- 集約キー

### FR-008 翻訳状態

翻訳状態は最低限以下を区別できること。

- 完全一致
- エラーコード一致
- パターン一致
- 未翻訳
- 翻訳失敗

### FR-009 カテゴリ

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

## 10. 翻訳仕様

### FR-010 翻訳パイプライン

翻訳は以下の優先順で評価すること。

1. 原文完全一致
2. コンパイラエラーコード一致
3. 正規化済みパターン一致
4. 未翻訳

### FR-011 技術識別子保護

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

### FR-012 日本語要約の責務

日本語要約は原文の意味を短く説明する。

日本語要約へ、原文から確定できない原因、修正方法、性能評価を混入してはならない。

補足情報を表示する場合は、翻訳ルールに明示的に登録された検証済み情報だけを使用し、日本語要約と区別すること。

### FR-013 未翻訳時の表示

翻訳ルールに一致しない場合は、原文をそのまま表示し、翻訳状態を`未翻訳`とする。

空文字、推測翻訳、機械的な単語置換だけの文章を日本語要約として表示してはならない。

### FR-014 ルールの追跡可能性

適用した翻訳ルールIDを詳細画面で確認できること。

翻訳ルールはVersion Controlで差分確認できる形式とし、ルール変更で既存メッセージの意味が変わる場合に追跡可能であること。

翻訳ルールの具体的な保存形式は未決定事項とする。

## 11. 集約・保持仕様

### FR-015 同一ログ集約

同一と判定したログは1行へ集約し、発生回数、初回発生時刻、最終発生時刻を更新すること。

集約キーには最低限以下を含めること。

- 正規化済み原文
- LogType
- カテゴリ
- ファイル
- 行

C#コンパイルイベントと通常ログイベントの両方で同一メッセージを取得した場合は、重複表示を抑止し、構造化情報が多い側へ統合すること。

### FR-016 Collapse切替

ユーザーは集約表示と個別表示を切り替えられること。

個別表示でも保持上限を超えて無制限に増加させないこと。

### FR-017 保持上限

初期値として最大10,000件の表示レコードを保持すること。

上限到達時は最も古いレコードから削除し、Editorのメモリを無制限に増加させないこと。

削除件数または破棄発生をウィンドウ上で確認できること。

## 12. UI仕様

### FR-018 基本レイアウト

UI Toolkitで以下の構成を持つこと。

1. 上部ツールバー
2. ログ一覧
3. 選択ログ詳細

ログ一覧と詳細はリサイズ可能な分割表示とする。

### FR-019 上部ツールバー

最低限以下を提供すること。

- Clear
- Pause
- Collapse
- Log表示切替
- Warning表示切替
- Error/Assert/Exception表示切替
- カテゴリ選択
- 翻訳状態選択
- 検索欄

### FR-020 ログ一覧

一覧には最低限以下を表示すること。

- 種別
- 発生回数
- 日本語要約または未翻訳原文
- カテゴリ
- 発生元
- 最終発生時刻

大量ログを前提として、全件分のVisualElementを常時生成しない仮想化リストを使用すること。

### FR-021 詳細表示

選択ログについて最低限以下を表示すること。

- 日本語要約
- 翻訳状態
- 翻訳ルールID
- 原文
- スタックトレース
- ファイル
- 行
- 列
- Assembly
- Shader Platform
- MessageDetails
- 初回発生時刻
- 最終発生時刻
- 発生回数

取得できない項目は非表示または`取得不可`とし、推測値を表示しないこと。

### FR-022 検索

検索は最低限以下を対象とすること。

- 原文
- 日本語要約
- ファイル
- カテゴリ
- エラーコード
- スタックトレース

検索文字列は大文字・小文字を区別しないこと。

### FR-023 コピー

以下を個別にコピーできること。

- 日本語要約
- 原文
- スタックトレース
- 詳細全体

### FR-024 ファイル移動

ファイルと行番号を解決できるログは、一覧のダブルクリックまたは詳細ボタンから外部コードエディタの対象行へ移動できること。

ファイルが存在しない場合、例外を発生させず移動不能であることを表示すること。

### FR-025 Pause

Pause中は受信ログを失わず待機列または保留領域へ保持し、一覧の反映だけを停止すること。

保持上限を超える場合は古いログを破棄し、破棄件数を表示すること。

### FR-026 Clear

Clearは本ウィンドウが保持するログだけを消去すること。

Unity標準Consoleの内容を消去してはならない。

### FR-027 外観

ラベル、Tooltip、空状態、エラー表示は日本語を優先する。

黒基調、白文字を基本とし、Error、Warning、Logは文字だけに依存せずアイコンまたは形状でも区別できること。

## 13. Editorライフサイクル仕様

### FR-028 購読管理

ウィンドウ有効化時に必要なイベントを1回だけ購読し、無効化または破棄時に必ず解除すること。

Domain Reload、Assembly Reload、ウィンドウ再生成後に重複購読を発生させないこと。

### FR-029 Hot Reload

UI ToolkitのVisual Tree再生成後も、保持中のログモデルと表示状態が破損しないこと。

Domain Reloadを跨いだログ履歴保持は初版の必須要件としない。

### FR-030 Editor専用分離

本機能のコードとアセットはEditor専用Assemblyへ分離され、Playerビルドへ含まれないこと。

Runtime Assemblyから本機能を参照させないこと。

## 14. 非機能要件

### NFR-001 スレッド安全性

`Application.logMessageReceivedThreaded`のコールバックは並列呼び出しを前提とし、共有状態への非同期アクセスで競合、破損、例外を発生させないこと。

### NFR-002 標準機能非侵襲

標準Console、`Debug.unityLogger`、既存`ILogHandler`、既存ログフィルタへ変更を加えないこと。

### NFR-003 公開API互換性

Unity 6000.3で公開されているAPIだけを使用すること。内部API、Reflection、非公開フィールドへの依存を0件とする。

### NFR-004 Editor応答性

1,000件のログを短時間に投入する検証で、ログ受信コールバック内にUI更新、翻訳、正規表現、ファイルI/Oが存在しないことをProfilerとコード監査で確認する。

メインスレッド側は1フレームの処理時間上限を持ち、ログ取り込みだけで長時間Editorを占有しないこと。

具体的な処理時間上限値は実装計画で計測環境とともに確定する。

### NFR-005 メモリ上限

保持件数上限を超えてログモデルが無制限に増加しないこと。

UI要素数は表示件数ではなく可視領域に依存すること。

### NFR-006 データ完全性

日本語要約生成の成否にかかわらず、受信した原文と取得済み診断位置を変更しないこと。

### NFR-007 オフライン動作

ネットワーク接続、API Key、外部サービス、外部プロセスを必要としないこと。

### NFR-008 セキュリティ・機密性

ログ内容、ファイルパス、スタックトレースを外部へ送信しないこと。

### NFR-009 保守性

ログ収集、分類、正規化、翻訳ルール評価、集約、UI表示を責務単位で分離すること。

`Manager`、`Controller`、`Util`、`Common`、`Helper`という曖昧な型を導入しないこと。

### NFR-010 命名・構成

- Namespace: `<RootNamespace>.UnityJapaneseConsoleWindow`
- private field: `_camelCase`
- public API/type/member: `PascalCase`
- enum: `E_UPPER_SNAKE_CASE`
- struct: `S_UPPER_SNAKE_CASE`
- const: `SCREAMING_SNAKE_CASE`
- コメント: 日本語で理由、制約、意図を記述

### NFR-011 テスト可能性

分類、正規化、識別子保護、翻訳ルール評価、集約キー生成はUnity Editor UIから分離し、入力と出力を固定したEditMode Testが可能であること。

### NFR-012 正確な表示

翻訳できない内容を翻訳済みとして扱わないこと。原因不明の内容を断定しないこと。取得できないPlatform、Assembly、行番号などを推測しないこと。

## 15. 受け入れ条件

### AC-001 ウィンドウ表示

**検証:** メニューからウィンドウを開く。

**合格:** 黒基調の一覧・詳細・ツールバーが表示され、Consoleエラーを発生させない。

### AC-002 通常ログ受信

**検証:** `Log`、`Warning`、`Error`、`Assert`、`Exception`を各1件発生させる。

**合格:** 全種別が一覧へ表示され、原文と種別が一致する。

### AC-003 別スレッドログ受信

**検証:** 別スレッドからログを発生させる。

**合格:** 競合例外、Unity APIスレッド例外、欠損によるウィンドウ停止が発生しない。

### AC-004 C#コンパイル情報

**検証:** テスト用のC#コンパイルエラーを発生させる。

**合格:** 原文、メッセージ種別、ファイル、行、列、Assembly情報が取得できる範囲で表示される。

### AC-005 Shaderコンパイル情報

**検証:** テスト用Shaderコンパイルエラーを発生させる。

**合格:** 原文が表示され、Shaderを解決できる場合はファイル、行、Severity、Platform、MessageDetailsが補完される。

### AC-006 既知ルール翻訳

**検証:** 登録済みC#エラーコードおよび登録済みUnityエラーパターンを発生させる。

**合格:** 日本語要約、翻訳状態、ルールIDが表示される。

### AC-007 識別子保持

**検証:** 型名、メソッド名、ファイルパス、Shader Keyword、数値を含む既知メッセージを翻訳する。

**合格:** 技術識別子が原文と同一文字列で日本語要約内に保持される。

### AC-008 未翻訳表示

**検証:** 未登録メッセージを発生させる。

**合格:** 翻訳状態が`未翻訳`となり、原文が欠損せず表示される。

### AC-009 集約

**検証:** 同一ログを100回発生させる。

**合格:** Collapse有効時に1行へ集約され、発生回数が100になる。

### AC-010 重複統合

**検証:** 同一C#コンパイルメッセージを通常ログ経路とCompilationPipeline経路で受信する。

**合格:** 二重表示されず、ファイル・行・列を持つ構造化レコードへ統合される。

### AC-011 フィルタと検索

**検証:** 複数種別・複数カテゴリ・翻訳済み・未翻訳ログを用意する。

**合格:** 種別、カテゴリ、翻訳状態、検索文字列の組み合わせで対象だけを表示できる。

### AC-012 ファイル移動

**検証:** ファイルと行番号を持つC#またはShaderエラーをダブルクリックする。

**合格:** 外部コードエディタで対象ファイルの対象行が開く。

### AC-013 PauseとClear

**検証:** Pause中にログを発生させ、Resume後に反映する。次にClearする。

**合格:** Pause中の表示更新が止まり、Resume後に保持ログが反映される。Clear後は本ウィンドウだけが空になる。

### AC-014 標準Console非侵襲

**検証:** 本ウィンドウ起動前後で同じログを発生させる。

**合格:** Unity標準Consoleの原文、件数、Logger挙動が本ツールにより変更されない。

### AC-015 購読重複防止

**検証:** Domain Reload、ウィンドウClose/Openを複数回実行後にログを1件発生させる。

**合格:** 本ウィンドウへ1件だけ追加される。

### AC-016 Player分離

**検証:** Player向けAssembly定義とビルド対象を確認する。

**合格:** 本機能のEditorコードがPlayerコンパイル対象へ含まれない。

### AC-017 大量ログ

**検証:** 1,000件のログを短時間に投入し、ProfilerとUI操作を確認する。

**合格:** コールバック内で禁止処理が実行されず、Editorが長時間操作不能にならず、保持上限と破棄件数表示が機能する。

### AC-018 内部API不使用

**検証:** コード検索と参照Assembly監査を行う。

**合格:** `UnityEditorInternal.LogEntries`、標準Console内部型、Reflectionによる非公開メンバーアクセスが0件である。

## 16. 初期翻訳対象

初版の翻訳辞書は最低限以下を対象候補とする。

1. C# Compiler
   - CS0103
   - CS0117
   - CS0120
   - CS0246
   - CS1061
   - CS1501
   - CS1503
2. Unity Runtime
   - `NullReferenceException`
   - `MissingReferenceException`
   - `InvalidOperationException`
3. Shader/HLSL
   - `undeclared identifier`
   - `syntax error`
   - `redefinition`
   - `cannot convert`
   - `Shader variant not found`
4. RenderGraph
   - 未初期化Attachment
   - RenderPass外操作
   - Global State変更禁止
5. Burst/Jobs
   - Managed object使用
   - NativeContainer安全性
   - Job dependency未完了

個別メッセージの正式な翻訳文とパターンは実装計画前に別途ルールカタログとして確定する。

## 17. 未決定事項

### UD-001 RootNamespace

`Specs/ProjectProfile.md`が`CHANGE_ME`のため、実装前にRootNamespaceを確定する必要がある。

### UD-002 翻訳ルール保存形式

候補はJSON、YAML、ScriptableObject、C#定義である。Version Control差分、Editor読み込み負荷、型安全性を比較して実装計画で決定する。

### UD-003 処理時間上限

メインスレッドの1フレーム処理時間または最大処理件数は、基準PCと計測方法を定義して実装計画で決定する。

### UD-004 初期翻訳辞書の範囲

初版で登録する具体的なエラー数、カテゴリごとの優先順位を決定する必要がある。

### UD-005 将来の外部翻訳

未知ログへの外部AIまたは翻訳API対応は初版対象外とする。将来追加する場合は、明示的な有効化、機密情報マスキング、通信先、API Key管理、キャッシュ、費用上限を別Specで定義する。

## 18. 実装前ゲート

実装へ進む前に以下を完了すること。

1. `UD-001` RootNamespace確定
2. 翻訳ルール保存形式確定
3. 初期翻訳ルールカタログ作成
4. `plan.md`作成
5. `tasks.md`作成
6. EditMode Test方針確定
7. 大量ログ計測条件確定

## 19. 参考資料

- Unity 6 `Application.logMessageReceivedThreaded`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Application-logMessageReceivedThreaded.html
- Unity 6 `CompilationPipeline.assemblyCompilationFinished`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Compilation.CompilationPipeline-assemblyCompilationFinished.html
- Unity 6 `CompilerMessage`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Compilation.CompilerMessage.html
- Unity 6 `ShaderUtil.GetShaderMessages`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ShaderUtil.GetShaderMessages.html
- Unity 6 `ShaderMessage`
  - https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ShaderMessage.html
- Unity 6 UI Toolkit Editor Window
  - https://docs.unity3d.com/6000.0/Documentation/Manual/UIE-HowTo-CreateEditorWindow.html
- Unity 6 UI Toolkit ListView
  - https://docs.unity3d.com/6000.0/Documentation/Manual/UIE-uxml-element-ListView.html
