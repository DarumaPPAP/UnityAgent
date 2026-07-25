---
name: unity-visual-direction
description: Use when designing, generating, revising, or reviewing Unity scenes whose success depends on beauty, composition, lighting, color, atmosphere, camera language, material presentation, or emotional impact. Produces a Visual Intent Contract and Beauty Review grounded in DarumaPPAP/Beautiful-Definition. Delegates technical rendering implementation to unity-rendering and bounded code changes to unity-implement. Does not treat compile success, feature count, Bloom, Fog, Light count, or capture generation as visual acceptance.
allowed-tools:
  - Read
  - Write
  - Edit
metadata:
  version: "1.0.0"
---

# Unity Visual Direction

Unity Sceneの美的方向性を、ユーザーの美的正本`DarumaPPAP/Beautiful-Definition`から取得し、生成前のVisual Intent Contractと生成後のBeauty Reviewへ変換するSkillです。

このSkillはVisual directionと美的受入判定を所有します。Renderer、Shader、Lighting API、Volume、Camera実装などの技術手順は`unity-rendering`へ委譲します。

## When to use

- 「美しいScene」「ハイエンドな絵」「画作りを良くしたい」
- Environment art、Lighting、Look Development、Color script
- Camera composition、Hero shot、Showcase capture
- Sky、Fog、Atmosphere、Reflection、Post Processを美的目的で調整
- Character presentation、Portrait、背景との分離
- 生成Sceneが美しいかをReference基準で評価
- HEVLL、Learning Scene、Visual demoなど、技術と画作りの両方を含む依頼

純粋なRenderGraph error、Shader compile failure、RenderQueue bug、性能監査だけにはPrimaryとして使用しません。その場合は`unity-incident-investigation`、`unity-rendering`、またはEvidence Skillを使います。

## Required references

Visual taskでは次を必要な範囲だけ読みます。

1. 現在のUser instruction
2. `SkillReferences/BEAUTIFUL_DEFINITION_INTEGRATION.md`
3. `DarumaPPAP/Beautiful-Definition/AGENTS.md`
4. `DarumaPPAP/Beautiful-Definition/Catalog/definitions.yaml`
5. Taskに一致するDefinition Profile
6. `DarumaPPAP/Beautiful-Definition/Definitions/CORE_BEAUTY_PRINCIPLES.md`
7. 生成前は`Templates/VISUAL_INTENT_TEMPLATE.md`
8. Review時は`Templates/BEAUTY_REVIEW_TEMPLATE.md`

全Reference画像を無条件に読み込みません。Scene type、Mood、Time of day、Subject scale、Camera distanceが一致するDefinitionを選びます。

## Delegates to

- `unity-specify` — 美的Goalを含む新規Scene仕様の受け入れ条件
- `unity-plan` — Scene、Lighting、Camera、Material、Postの責務分離
- `unity-rendering` — URP、Renderer、Light、Volume、Camera、Shaderの技術契約
- `unity-implement` — 承認済みVisual Intentに基づく限定実装
- `unity-review` — Scope、Compatibility、Evidenceを含む最終受入レビュー
- `unity-incident-investigation` — 実装後に表示破綻やEditor / Player差が出た場合

専門手順をこのSkillへコピーしません。

## Inputs

- Userが示した美的GoalまたはReference
- Scene type、Subject、Mood、Time of day
- Unity / URP / Platform制約
- 利用可能なAssetと生成可能範囲
- Camera captureまたはVisual evidence
- 既存のVisual Intent Contract

Repositoryから解決できる情報を先に取得し、不足する美的判断だけを人間へ確認します。

## Step 1 — Classify the visual task

次を分類します。

- Scene generation
- Visual redesign
- Lighting / LookDev
- Camera / Composition
- Character presentation
- Beauty review
- Negative-example analysis

技術修正だけのTaskを、美的Taskへ無理に拡張しません。

## Step 2 — Retrieve the beauty definition

1. `Catalog/definitions.yaml`から候補を検索する
2. User instructionとの一致度を確認する
3. Core Principles、Style Profile、Positive rule、Disqualifierを読む
4. Referenceの直接観測とAI推論を分離する
5. 一致するDefinitionがなければ`CONTEXT_REQUIRED`とする

一般的な美術知識でユーザーの明示的な好みを上書きしません。

## Step 3 — Produce the Visual Intent Contract

実装前に最低限次を確定します。

- Selected Definition ID
- Emotional intent
- Experiential subject
- Composition hierarchy
- Camera language
- Lighting hierarchy
- Color script
- Foreground / midground / background
- Material and reflection intent
- Atmosphere role
- Post-process limits
- Positive rules
- Disqualifiers
- Required captures
- Human review questions

SceneのGoalを「機能を入れる」「Objectを配置する」にしません。

## Step 4 — Translate intent into bounded technical work

Visual Intentを技術要件へ変換するときは次を守ります。

- 大域光を先に設計し、Light数を目的にしない
- CameraとCompositionをGeometry detailより先に固定する
- Color scriptをColor gradingだけへ押し込まない
- Reflection、Fog、Bloom、DOFをDepthと視線誘導へ限定する
- Referenceの固有Character、Logo、Architecture、配置を直接複製しない
- Runtime / Editor / Platform制約を`unity-rendering`へ渡す

承認されていないController、Manager、追加Camera、Debug UIを作りません。

## Step 5 — Review visual evidence

Beauty Reviewは次を分離します。

### Beauty gate

- Emotional clarity
- Composition and gaze control
- Lighting hierarchy
- Color script
- Depth and atmosphere
- Material contrast
- Originality and world coherence
- Disqualifier check

### Technical gate

- Flicker
- Ghosting
- Aliasing
- Shadow artifact
- Overexposure
- Reflection artifact
- Performance evidence

Compile成功、PlayMode成功、Capture生成はBeauty gateの通過を意味しません。

## Step 6 — Route human feedback into learning

Human feedbackを次へ分類します。

- Definition correction
- Preference expansion
- Context exception
- Negative example
- Weight adjustment

一度の指摘を普遍ルールへ即時昇格せず、`Beautiful-Definition/Observations/`へ候補として記録します。User承認後にDefinitionへ反映します。

## Verification levels

実施済みの最上位だけを報告します。

1. Definition retrieved
2. Visual Intent Contract reviewed
3. Static Scene design reviewed
4. Unity compilation passed
5. Editor capture produced
6. Runtime / Player capture produced
7. Human beauty review completed
8. Human accepted

Level 5以前を`美しいことを確認済み`と表現しません。

## Scope — what this Skill does not do

- Unity APIやRenderGraph実装の詳細を所有しない
- GPU性能を美的Scoreへ混ぜない
- Reference作品を複製しない
- User approvalなしにDefinitionを`approved`へ変更しない
- Human reviewなしに`VISUAL_ACCEPTED`としない
- 「高機能」「高負荷」「大量のLight」を美しさとして扱わない

## Output contract

- Selected Definition IDと選定理由
- Visual Intent Contract
- Direct observation / Inference / Human-confirmed preferenceの区別
- Positive rulesとDisqualifiers
- 技術Skillへの委譲事項
- Visual evidence path
- Beauty Review result
- Human approval status
- Learning update候補
- 未検証事項

## Checklist

- [ ] Visual taskとして正しく分類した
- [ ] Beautiful-Definitionを取得した
- [ ] User instructionをDefinitionより優先した
- [ ] Visual Intent Contractを実装前に作成した
- [ ] 技術機能数を美しさの代理にしていない
- [ ] Beauty gateとTechnical gateを分離した
- [ ] Referenceの表面コピーを避けた
- [ ] Human approval statusを正確に報告した

## Common mistakes

- Bloom、Fog、Emissionを増やして高級感を作ろうとする
- Point / Spot Lightを大量に追加する
- CameraをScene全体が見えるEditor視点へ置く
- Materialをすべて高Smoothnessへ寄せる
- Reference画像の色だけをLUTで模倣する
- Compile成功をVisual acceptanceと誤認する
- 一つのReferenceから普遍的な美的原則を断定する
