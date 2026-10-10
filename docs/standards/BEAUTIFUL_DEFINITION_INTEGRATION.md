# Beautiful-Definition Integration

## Source of truth

Visual quality、Beauty、Composition、Lighting mood、Color script、Look Development、Atmosphere、Camera presentationの美的判断は、次のRepositoryを正本とします。

- Repository: `DarumaPPAP/Beautiful-Definition`
- Entry: `AGENTS.md`
- Index: `Catalog/definitions.yaml`

UnityAgentへ美的Definition本文を複製しません。複製すると更新差分が発生するため、Task実行時に正本から取得します。

## Trigger conditions

次の表現または成果条件を含む場合、`unity-visual-direction`をPrimaryまたはSecondaryとして選びます。

- 美しい、綺麗、ハイエンド、映える、雰囲気を良くする
- Scene、Environment、Lighting、LookDev、Composition、Hero Shot
- Sky、Fog、Reflection、Post Processを画作り目的で調整
- Character portrait、Camera framing、Color script
- 参考画像のような美しさを分析または再現原則へ変換
- Visual qualityを採点、レビュー、改善

純粋な描画バグ、性能、Shader compile、RenderGraph correctnessだけの場合は必須ではありません。

## Retrieval contract

1. `Beautiful-Definition/AGENTS.md`を読む
2. `Catalog/definitions.yaml`から候補を検索する
3. Taskに一致するDefinitionだけを読む
4. Core Principlesを条件付きで読む
5. Reference metadataが必要な場合だけ該当Setを読む
6. Visual IntentまたはReview Templateを使う

全Referenceを一括読込しません。

## Authority order

1. 現在のUser instruction
2. Beautiful-Definitionの`approved`
3. Beautiful-Definitionの`active-draft`かつUser-confirmed positive basis
4. Reference metadataのUser note
5. AI Observation
6. 一般的な美術知識

UnityAgent内の技術規約は、美的好みを上書きしません。Beautiful-DefinitionもUnity API、互換性、性能、安全性の契約を上書きしません。

## Required output

生成前:

- Selected Definition ID
- Visual Intent Contract
- Positive rules
- Disqualifiers
- 技術実装への変換事項

評価後:

- Beauty gate result
- Technical gate result
- Human approval status
- Learning update候補

## Failure handling

### Repository unavailable

`Beautiful-Definition`へアクセスできない場合は、美的正本を取得済みと推測しません。

- 既存Spec内にDefinition IDと必要内容が埋め込まれている: その範囲だけ使用
- UserがReferenceを現在の依頼へ添付している: Reference由来と明記して暫定分析
- どちらもない: `CONTEXT_REQUIRED`

### Definition mismatch

Taskに一致するDefinitionがない場合、近いStyleを無理に適用しません。
新しいObservationまたはStyle Definition候補として扱います。

### Visual rejection

Humanが拒否した場合、技術実装を成功扱いのままVisual acceptanceにしません。
FeedbackをDefinition correction、Preference expansion、Context exception、Negative example、Weight adjustmentへ分類します。

## Human boundary

- `VISUAL_ACCEPTED`はHuman approvalが必要
- Definitionの`approved`化はHuman decision
- Reference作品の固有Asset、Character、Logo、Architectureの複製は禁止
- AIは美的ScoreだけでPR Mergeを決定しない
