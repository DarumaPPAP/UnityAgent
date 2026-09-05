# Astra向けAgent指示監査

- 調査日: 2026-09-05
- 対象: DarumaPPAP/UnityAgent
- Base commit: `e1ecd31a8532c09ae0bdb73af4245da276e5b41d`
- 範囲: Agentの指示・適用条件。モデル既定値、API、Runtimeの承認実装を移行する変更ではない。

## 公式根拠

OpenAIの[GPT-6 Astra guide — Prompting best practices](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices)は、Skills / AGENTS.mdの指示監査を強く推奨している。確認した論点は、依頼の完遂、ユーザー指示との優先関係、停止理由の明示、委譲条件、変更に見合う検証範囲である。これは全ファイルの削除や承認Gateの撤廃を要求するものではない。

[AGENTS.md公式ガイド](https://learn.chatgpt.com/docs/agent-configuration/agents-md)と[Codex best practices](https://learn.chatgpt.com/guides/best-practices)も参照した。以下の修正はUnityAgentの既存契約に当てはめた設計判断であり、モデル性能の測定結果ではない。

## 調査方法と指示面

Root AGENTS.md、User/Risk/Approval Policy、Route/Context catalog、実行Runner、検証入口を確認した。23 Skillsと9 Agent定義から停止・承認・委譲・検証条件を検索し、変更対象5 Skillsと統括Agent、および隣接するSpecify等の手順を精読した。Skill全体の再設計や全参照文書の逐語監査ではない。

## Findingsと対応

| ID | 場所・観測した指示 | 影響の可能性 | 対応 |
|---|---|---|---|
| A01 | AGENTS.mdの14段階Bootstrapと重複する責務制約 | Repository保守にも全Runtime起動が必要と解釈される | 日常保守とProduction実行を区別。詳細契約を参照先へ移動 |
| A02 | unity-implementの一律の次Task停止 | 全体実装の依頼も一件完了で止まる | 一回のSkillの境界と依頼全体の完了を区別。依頼済みTaskは呼出元が順次選択 |
| A03 | unity-plan / unity-tasksの承認済み前提 | 依頼済み工程にも形式的な再承認を求める | 現在の依頼と既存の承認を先に照合。Policyの実際のGateを保持 |
| A04 | implement / tasks / safe-patchの最強検証指定 | 小規模修正から無関係な検証まで拡大する | 変更契約・受入条件・必須Gateに基づいて選び、反復には具体的根拠を要求 |
| A05 | 統括AgentのWorkflow / Delegate to | 読取監査から修正への拡張、全Agentの起動と解釈される | Skill適用と別Agent起動を区別し、読取のみ依頼の境界を明記 |
| A06 | unity-review InputsのProject Profile / Constitution | 検出Factや現在Policyより過去文書を優先する | User Policyと検出Factを明示し、ProjectProfileを不足FactのFallbackに限定 |
| A07 | safe-patchのfast path停止 | 安全な調査まで終了する | 推測Patchの停止と許可済み調査の継続を区別 |

Root指示には、途中の訂正への追従、具体的な停止理由、変更に応じた出力密度も記載した。新しい一律承認、モデル固定、全作業の並列化は追加していない。

## Policyを失わないことの確認

- `Policy/User/user-policy.yaml`を含むPolicyディレクトリは無変更。命名、コメント体系、Shader分岐、互換性、承認条件を保持。
- 旧AGENTS.mdのセクション2〜8は[Runtime Bootstrap Contract](../runtime-bootstrap-contract.md)へ逐語的に移動し、元本文との一致を確認。
- RootからProduction実行とAuthority変更時の読込先を明示。Routeの `required_policy_clauses` / Policy provenanceもRootに保持。
- Context / Orchestration / Runtime / Persistence / Operations / Evalの実行・機械可読契約は無変更。
- BootstrapはUTF-8で13,447 → 5,552 bytes（約58.7%減）。これはRootのサイズ差であり、実リクエストの総token削減率や高速化率ではない。Productionで詳細契約を読む場合はそのContextも加わる。

## 検証結果

| 検証 | 結果 |
|---|---|
| `python Tools/validate_all.py` | 成功。既存Validator群と8 test suites / 320 testsを通過 |
| 変更した5 Skillsのquick_validate | 5/5成功 |
| 23 Skillsの既存構造検証 | 0 errors / 25 warnings。変更前とFinding配列が完全一致 |
| User Policyと機械可読契約 | 無変更をdiff確認 |
| Bootstrap詳細移動 | 元のセクション2〜8との本文一致を確認 |
| `git diff --check` | 成功 |

初回の検証は環境のjsonschema不足で失敗した。CI定義にある依存を作業用ディレクトリへ導入後、検証一式を再実行して成功した。初回失敗を成功として扱っていない。検証ToolやCI Gateを緩める変更もない。

## 実動作の確認に残ること

AstraによるProduction smoke、Unity Editor / Player / 実機計測は今回未実施。既存fixture・contract検証の成功は、Astraの停止率・品質・速度の改善を証明しない。既存Golden / baselineを変更して改善を演出していない。

導入後は同一Task・実行条件で旧指示と新指示を比較し、完了率、不要な確認回数、必要証拠の欠落、Scope逸脱、tool call数・時間を観測する。確認すべき境界は次のとおり。

| 依頼条件 | 期待する観測 |
|---|---|
| 局所C#修正、Compile環境なし | 原因が一意なら限定Patchを作り、Compileはunavailableと報告 |
| Task Aのみ指定 | Aで終了しBへ変更しない |
| A〜Cまで実装依頼済み | 各Taskの条件を守りCまで継続 |
| Planだけ作成依頼 | Planを返しProduction codeを変更しない |
| Scene変更・Bakeの承認不足 | 独立した調査と差分案を準備し、該当操作直前のGateで停止 |
| 文書修正・必須Gate成功 | 無関係なPlayerや性能検証を要求しない |
| Shader監査のみ | Findingを返しShaderを勝手に修正しない |

これらは今後の実動作比較の観測条件であり、実行済みテスト結果ではない。
