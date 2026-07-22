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

## D-004 外部翻訳APIを採用しない

Google Cloud Translation、DeepL、Azure Translator、OpenAI、LibreTranslateなどの外部翻訳機能を仕様から削除する。

API Key、Cloud Account、課金設定、ネットワーク通信を必要としない。

**理由:** 完全無料かつローカル完結で運用し、従量課金、サービス停止、認証情報管理、ログ外部送信を避けるため。

## D-005 ローカル辞書育成方式を採用する

公開ソースから生成した翻訳ルールと、実際に発生した未翻訳ログから追加した翻訳ルールを使用する。

翻訳できないログは原文を表示し、未翻訳Corpusへ記録する。

**理由:** 未知文章の一般翻訳は行えないが、Unity開発で実際に使う診断メッセージの翻訳率を継続的に高められるため。

## D-006 翻訳評価順を固定する

翻訳評価順は次とする。

1. Exact
2. DiagnosticCode
3. Template
4. Pattern
5. Untranslated

**理由:** 安定した一致方法を優先し、Regex依存と誤一致を最小化するため。

## D-007 ルール正本をカテゴリ別JSONとする

翻訳ルール本体は、カテゴリ別に分割したJSONファイルとしてVersion Controlへ保存する。

**理由:** 人間とCodexが差分レビューしやすく、巨大なUnity YAML Assetの競合と破損リスクを避けるため。

## D-008 巨大な単一ScriptableObjectを使用しない

全翻訳ルールを一つのScriptableObjectへ格納しない。

ScriptableObjectはManifest参照や小規模設定に限定する。

**理由:** 数万件規模のInspector編集、Git差分、Merge Conflict、Import負荷、Asset破損リスクを避けるため。

## D-009 コンパイル済みDBをLibraryへ生成する

分割JSONを検証・コンパイルし、次へ高速検索用DBを生成する。

```text
Library/UnityJapaneseConsoleWindow/CompiledRuleDatabase.bin
```

生成物はGit管理しない。

**理由:** 正本の可読性と、Editor実行時の検索速度を両立するため。

## D-010 ExactとDiagnosticCodeをDictionary化する

Exact RuleとDiagnostic Code RuleをDictionary Indexへ格納する。

TemplateとPatternはCategory別Indexへ分割する。

**理由:** ログごとの全Rule線形走査を避け、大規模辞書でも検索コストを安定させるため。

## D-011 Patternは最後の手段とする

Exact、DiagnosticCode、Templateで表現できない場合だけPatternを使用する。

Regex Timeoutと危険Pattern検証を必須とする。

**理由:** 誤一致、Catastrophic Backtracking、保守性低下を防ぐため。

## D-012 公開ソースImporterは候補生成までとする

C# Diagnostics、Roslyn、.NET Runtime、UnityCsReference、Unity Package、Shader Compilerなどの公開ソースからCandidate Ruleを生成する。

Candidateを自動でApprovedへ昇格させない。

**理由:** 抽出結果の誤り、動的文字列、ライセンス、翻訳品質を人間またはレビュー工程で確認する必要があるため。

## D-013 Importerはネットワーク通信を行わない

Importerの入力は、ローカルCheckout、ローカルPackage、保存済みSource Snapshot、CSV、JSONに限定する。

**理由:** 通常利用を完全オフラインに保ち、Web仕様変更と自動Scraping依存を避けるため。

## D-014 出典とライセンスを追跡する

各RuleはSource IDを持ち、Source ManifestへVersion、Commit、License、Redistribution Policy、Importer Versionを記録する。

ライセンスが不明または再配布不可のSourceは公開Rule SourceへCommitしない。

**理由:** 公開されている情報と再配布可能な情報は同一ではないため。

## D-015 100%網羅を保証しない

Unity C++ Engine内部、GPU Driver、OS、非公開Platform SDK、Asset Store Package、プロジェクト固有ログを事前に完全収集できるとは扱わない。

**理由:** すべてのログ文字列が公開・固定・再配布可能ではないため。

## D-016 未翻訳ログCorpusを保持する

未翻訳ログを次へ重複集約して保存する。

```text
Library/UnityJapaneseConsoleWindow/UntranslatedCorpus.json
```

同一ログは一件として保持し、Occurrence Countを更新する。

**理由:** 実プロジェクトで必要なログから優先的に辞書を育てるため。

## D-017 Corpusから辞書候補をExportする

未翻訳ログをJSONまたはCSVへ出力し、Codexや人間が翻訳Rule候補を生成できるようにする。

UnityJapaneseConsoleWindow自体はCodexやLLMを呼び出さない。

**理由:** Unityツールを外部サービス非依存に保ちながら、既存のAIコーディング運用を利用できるため。

## D-018 未承認ルールを本番検索に使用しない

Rule Statusを`Candidate`、`Reviewed`、`Approved`、`Deprecated`、`Rejected`に分ける。

Console翻訳へ使用するのは`Approved`だけとする。

**理由:** 自動抽出または自動生成された誤ルールが表示品質を破壊することを防ぐため。

## D-019 原文とStackTraceを必ず保持する

日本語訳が存在しても、原文、StackTrace、取得済み診断位置を保持する。

StackTraceは翻訳しない。

**理由:** 翻訳は補助情報であり、調査の正本はUnityまたはCompilerの原文だから。

## D-020 IMGUIへ一本化する

Editor UIはIMGUIで構成し、`UnityJapaneseConsoleWindow.OnGUI`、`ConsoleWindowGui`、`ConsoleLogList`を正式UI経路とする。

UI Toolkit、UXML、USSの未使用二重実装は削除する。

**理由:** Unity標準ConsoleWindowに近いデザインと操作感へ寄せやすく、現実装も可視行だけを描画する構成を持つため。

## D-021 Unity標準Consoleのデザインへ寄せる

上部ツールバー、ログ一覧、下部詳細ペインの3領域構成とし、EditorStyles、標準Consoleアイコン、Unity Themeを優先して利用する。

過剰なカードUI、角丸、影、独自Accent Colorを使用しない。

**理由:** Unity Editor内で違和感なく利用でき、標準Consoleからの移行コストを下げるため。

## D-022 同一ログのObservationを発生回数分保持しない

同一ログは`OccurrenceCount`で回数を表し、同一内容のObservationを全件保持しない。

1集約ログあたりのObservation初期上限を8件とする。

**理由:** 同一ログ大量発生時の累積コピー、二次的な処理量増加、メモリ増加を防ぐため。

## D-023 原因推測・自動修正を対象外とする

日本語訳へ、原文から確定できない原因や修正方法を混入しない。

ソースコードの自動変更も行わない。

**理由:** 翻訳機能と診断・修正機能の責務を分離するため。

## D-024 収集寿命をウィンドウ寿命へ合わせる

ウィンドウ有効化時に収集イベントを購読し、無効化または破棄時に解除する。

Window CloseまたはAssembly Reload前にCorpusと生成中データを安全にFlushする。

**理由:** mutable static状態、Singleton、常駐Controllerを導入せず、所有者と寿命を明確にするため。

## D-025 Editor専用とする

本機能、Rule Compiler、Importer、CorpusはEditor専用Assemblyへ分離し、Player、IL2CPP、実機ログ収集には使用しない。

**理由:** Playerへ不要なデータ、File I/O、Editor依存を持ち込まないため。

## D-026 標準Consoleとの状態同期を行わない

Clear、Collapse、Pause、Filter状態は本ウィンドウ内だけで管理する。

**理由:** 標準Console内部APIへ依存せず、動作境界を明確にするため。
