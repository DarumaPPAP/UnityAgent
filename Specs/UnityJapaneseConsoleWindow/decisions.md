# UnityJapaneseConsoleWindow Decisions

- FeatureName: `UnityJapaneseConsoleWindow`
- Status: Draft
- LastUpdated: 2026-07-22

## D-001 専用Editor Windowとして実装する

Unity標準Consoleの表示置換ではなく、標準Consoleと並行して利用する専用Editor Windowとする。

**理由:** 標準Console内部状態への依存を避け、Unity更新時の互換性リスクを抑えるため。

## D-002 公開APIだけを使用する

通常ログは`Application.logMessageReceivedThreaded`、C#コンパイル情報は`CompilationPipeline.assemblyCompilationFinished`、Shader詳細は解決可能な場合に`ShaderUtil.GetShaderMessages`を使用する。

**理由:** `UnityEditorInternal.LogEntries`やReflectionによる非公開API利用を避けるため。

## D-003 標準Loggerを差し替えない

`Debug.unityLogger`および既存`ILogHandler`を変更しない。

**理由:** 他のツール、Package、プロジェクト固有Loggerの挙動へ副作用を与えないため。

## D-004 初版はオフラインの決定論的翻訳とする

初版はVersion Controlで管理できるローカル翻訳ルールだけを使用する。外部AI、外部翻訳API、ネットワーク通信は使用しない。

**理由:** ログ、パス、スタックトレースの外部送信を避け、同一入力から同一結果を得るため。

## D-005 未知メッセージを推測翻訳しない

翻訳ルールへ一致しないログは`未翻訳`として原文を表示する。

**理由:** 技術識別子の破壊や誤訳を避けるため。

## D-006 原文を必ず保持する

日本語要約が存在しても、原文、スタックトレース、取得済み診断位置を保持する。

**理由:** 翻訳は補助情報であり、調査の正本はUnityまたはコンパイラの原文だから。

## D-007 原因推測・自動修正は初版対象外とする

日本語要約へ、原文から確定できない原因や修正方法を混入しない。ソースコードの自動変更も行わない。

**理由:** 翻訳機能と診断・修正機能の責務を分離するため。

## D-008 収集寿命はウィンドウ寿命へ合わせる

ウィンドウ有効化時に収集イベントを購読し、無効化または破棄時に解除する。ウィンドウが閉じている間のログは収集しない。

**理由:** mutable static状態、Singleton、常駐Controllerを導入せず、所有者と寿命を明確にするため。

## D-009 UI Toolkitと仮想化リストを使用する

Editor UIはUI Toolkitで構成し、大量ログ一覧は仮想化可能なListViewを使用する。

**理由:** ProjectProfileのUI方針へ合わせ、全件分のVisualElement生成を避けるため。

## D-010 Editor専用とする

本機能はEditor専用Assemblyへ分離し、Player、IL2CPP、実機ログ収集には使用しない。

**理由:** 目的がUnity Editor上の開発支援であり、Playerへ不要な依存とコードを持ち込まないため。

## D-011 標準Consoleとの状態同期を行わない

Clear、Collapse、Pause、フィルタ状態は本ウィンドウ内だけで管理する。

**理由:** 標準Console内部APIへ依存せず、動作境界を明確にするため。

## D-012 翻訳と補足を分離する

日本語要約は原文の意味だけを扱う。検証済みの補足を将来追加する場合は別フィールドとして表示する。

**理由:** 翻訳結果へ推測情報が混ざることを防ぐため。
