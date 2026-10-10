---
name: content-import-analysis
description: Use when analyzing observed Unity texture or audio importer settings, or Addressables entries, to prepare a project-specific change plan without applying it.
---

# Content Import Analysis

Texture、Audio、Addressablesの観測値から、Project固有の判断に従って変更候補を作る。ContentSubAgentの登録、Provider選択、Asset変更は行わない。

## Input boundary

Unity Projectと対象Assetを特定し、ImporterやAddressablesの現在値を実際のProjectから観測する。`tools/content_pilot/content_analysis.py`へ渡す辞書は観測入力であり、`evidence_ref`が含まれていても同Toolはその参照を検証しない。結果の`evidence_level: input_observation_only`をEditor検証済みと扱わない。

Textureの圧縮形式とFlat Normalの閾値はProject Decisionから受け取る。未決定の値は補完しない。Max Size未指定なら変更しない。Normal分類には明示された閾値、最小サンプル数、flat sample fractionを使う。このfractionは統計的信頼度ではない。サンプル採取方法と対象範囲も記録する。現在のImporter formatが未観測なら`candidate_only`で止め、変更Planと呼ばない。

AudioはLoad Type、Compression Format、Quality、Preload、Load in Background、Platform Override、Original Sizeを観測する。既存Platform Overrideを保持し、Project Decisionに指定されたFieldだけを変更候補にする。

AddressablesはPackage、Settings、Group、現在のAddress、Revisionを観測する。Analyzeで現状を確定し、Planには対象Group、Address、期待Revisionを含める。PackageやSettingsが無ければ不足状態を返し、存在を仮定しない。

旧`addressables.get_support_matrix`の知識境界を維持する。旧Toolの利用可否を評価する場合は、Addressables Packageの導入・Versionと旧Backendの有無を別々に観測する。現行のread-only分析は旧Backendを必要としない。Settingsを自動作成せず、自動Saveもしない。Content Build、Remote Content Update、Platform固有Content BuildはこのPilotの対象外。旧SourceがAddressables 2.x互換性を未検証としていた事実を、現行Pilotの互換性保証に読み替えない。

## Output Contract

Tool出力の`observed`、`proposed_changes`、`approval_required`、`applied`を分けて報告する。Textureの`proposed_format`も未適用の候補である。Applyする場合は別のUnityAgent実行経路で承認、現在Revision、exact diffを確認する。Pilotの出力だけでApply成功や品質改善を宣言しない。

## Checklist

- 入力が現在のProject、Asset、Platformから観測されたか確認する。
- Project Decisionの出所と適用範囲を明示する。
- 未観測のImporter設定や圧縮結果を推測しない。
- 変更候補とApply結果、Repository fixtureとEditor結果を区別する。

## Common Mistakes

- BC1/BC3/BC4/BC5の例を全Projectの既定値にする。
- Flat Normal候補を見た目や画質の検証済みと扱う。
- Addressables Planを承認済み変更として実行する。
