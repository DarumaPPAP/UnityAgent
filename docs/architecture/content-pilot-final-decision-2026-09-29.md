# Content Pilot 最終評価

## 結論

**ContentSubAgent Decision: `KEEP_AS_SKILL_TOOL`。** 現行のTexture、Audio、Addressablesは、入力済みの観測値とProject Decisionから読み取り分析または変更Planを作る決定論的Toolである。独立したReasoning Loop、Provider選択、Approval判断を必要とする実測は得られていないため、SubAgentへ昇格させない。ContentSubAgentのProduction昇格には別途Human Decisionが必要である。

## 確認した範囲

| 評価項目 | 今回の結果 | 限界 |
|---|---|---|
| Texture Pilot | Fixture PASS。Project Decisionがある場合だけFormat候補を返す。Flat Normalでは距離閾値、Sample方式・件数、Flat比率、分類に用いた値、制約を保持する。Max Sizeは指定がなければ変更しない | Samplingの代表性、画質、Platformのメモリは未測定。`confidence` は入力Sample内のFlat比率で、統計的信頼度ではない |
| Audio Pilot | Fixture PASS。Load Type、Compression Format、Quality、Preload、Background Load、Platform Override、Original Sizeを観測入力とし、AnalyzeとChange Planを分離する | 実Importerの読み取りと音質は未検証 |
| Addressables Pilot | Fixture PASS。Package、Settings、Group、Revisionが不足すればPlanを拒否し、Applyは実行しない | 実Package、Asset、Groupでの動作は未検証 |
| Context size | 独立したContent Specialist Contextを生成していないため未計測 | 実TaskのContext byte数とToken数は収集していない |
| Decision complexity | 3種類の明示的な入力契約とProject Decisionの比較で処理できる | 複雑な実案件に対する独立Reasoningの必要性は未評価 |
| Tool selection error | 実Task Traceなし。件数は未計測 | 0件とは判定しない |
| Cross-domain ambiguity | 各Toolの責務はTexture Import、Audio Import、Addressables Planとして分離される | 実Taskの曖昧な依頼でのRoute正確性は未評価 |
| Repeatability | 同一Fixture入力から同じ結果を2回生成し、入力に変更がないことをTestで確認 | Live Unity状態の変動は含まない |
| Required approvals | 変更Planに `approval_required: true`。全て `applied: false` | 承認後のApply経路はこのPilotの範囲外 |
| Evidence completeness | 結果は `input_observation_only`。入力にEvidence Refがなければ `input_unverified` と明示 | Live Editor・Player・Target Device Evidenceはない |

Project固有のTexture圧縮形式はProject Decisionで与える。BC1 / BC3 / BC4 / BC5をUnity全体の既定値として固定しない。AddressablesのSettings生成、Group生成、Save、Build、Remote Content Updateは自動実行しない。

今回の判定を見直す条件は、実Task TraceでSkill Context肥大、Importer Decisionの衝突、頻繁なDomain Reasoning、Tool選択誤り、独立したEvidenceまたはApproval Loopの必要性が複数確認された場合である。その際はA/B/C比較とLive Evidenceを収集し、現行のSkill + ToolをBaselineにする。
