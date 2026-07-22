# Comment Review Checklist

日本語コードコメントをProductionまたはLearningプロファイルで監査する。

## Review Order

1. コメントと実装の矛盾。
2. Unity API、URP、RenderGraph、Shader、Burst、Jobsに関する誤り。
3. 存在しない仕様、実測、性能改善率の断定。
4. 理由、制約、寿命、所有権、破綻条件の欠落。
5. コードを復唱するだけのコメント。
6. 重複、長文化、処理の分断。
7. XMLドキュメントの契約不足。
8. `TODO`、`FIXME`、`WORKAROUND`の解除条件不足。

## Required Checks

- Unityライフサイクルと実行順の説明は正しいか。
- EditorとPlayer、SceneViewとGame Cameraを混同していないか。
- RenderGraphのTextureHandle、Pass依存、Read/Write、Global Stateの説明は正しいか。
- Motion Vector、History、Reprojection、Disocclusionの前後関係を誤っていないか。
- Shaderの座標空間、補間、精度型、分岐、Texture Sampleの説明は正しいか。
- NativeContainer、JobHandle、Dispose、Burst制約の説明は正しいか。
- 実測していない性能効果を確定表現していないか。
- 「高速化のため」など、理由として不十分な表現がないか。
- コメントがなくても分かる処理へ過剰な説明を付けていないか。

## Severity

- Critical: 誤実装、データ破壊、リソースリーク、描画破綻を誘発する。
- Major: 仕様、寿命、所有権、実行順、性能判断を誤解させる。
- Minor: 冗長、重複、表現不統一、軽微な不足。
- Suggestion: 任意の可読性改善。

## Output Format

```text
- Severity:
- File:
- Location:
- Problem:
- Evidence:
- Recommended comment:
- Code change required: Yes / No
```

問題がない項目を水増しして報告しない。

## Auto-fix Policy

- コメントのみで修正可能ならコメントだけを変更する。
- コードとコメントのどちらが正しいか判断できない場合は修正せずFindingとして残す。
- 性能根拠がない数値は削除し、「要計測」へ変更する。
- 履歴説明は削除し、必要ならIssue、PR、`decisions.md`へ移すよう提案する。
- 学習用コメントが本番コードを分断している場合はMarkdown資料への分離を提案する。

## Completion Report

- 対象プロファイル: Production / Learning
- 監査ファイル数
- Critical / Major / Minor件数
- 自動修正したコメント
- 判断保留のFinding
- コード変更の必要性
