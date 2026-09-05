<!-- unityagent-bootstrap-map:v3 -->
# UnityAgent Bootstrap Map
> `bootstrap_map_only: true`

`AGENTS.md` は起動用の地図です。詳細規約を複製せず、必要なCanonical Sourceへ委譲します。

## Authority and scope

実行環境の上位指示・権限を守った上で、Repository内の優先順は次のとおりです。

1. 今回のユーザー明示指示（進行中の訂正・範囲指定を含む）
2. `Policy/User/user-policy.yaml`
3. 対象Project固有Policy
4. Unity Domain Standard
5. 外部Reference
6. 一般的Best Practice

最初に[User Policy](Policy/User/user-policy.yaml)を読む。Skill、Agent定義、例、過去の監査記録で今回の依頼やUser Policyを上書きしない。Policyの削除・簡略化は同Policyの保護契約に従う。対象ディレクトリ固有の指示も確認する。

## Work through the authorized request

- 「作って」「修正して」は実作業の依頼として扱い、調査・計画だけで終了しない。通常の実装判断は既存コードと依頼から決める。Project Fact・未知のBindingを捏造しない。
- ユーザーが一件だけ指定したらその境界で止める。複数Taskを依頼済みなら、一件ごとの境界と検証を守り、依存順に依頼範囲の完了まで進める。Skill一回の終了はユーザー依頼全体の終了とは限らない。
- 既存の承認が現在の操作・対象・差分条件を満たすかを先に確認する。承認済み内容を質問し直さない。[Approval Policy](Policy/Approval/approval-policy.yaml)が要求する承認・Revision・Exact Diff・Mutation Scopeは省略しない。
- 不足情報が結果や互換性を変える場合は、取得できる証拠を先に調べ、既に許可された独立作業とレビュー可能な差分を準備する。停止時は該当ファイル・条項・適用理由・不足条件を示す。実行権限の拒否を別経路で回避しない。
- 途中の質問には答え、元の目標も継続する。ユーザーが取消・変更した場合はそれに従い、完了済み作業を不必要にやり直さない。

## Select only the needed path

| 作業 | 読むもの・実行経路 |
|---|---|
| UnityAgent自身の文書・Skill・コード保守 | 対象ファイル、直接参照、関連する検証。Unity Projectの起動を前提にしない |
| Unity開発TaskをUnityAgent Runtimeで実行 | 下記Production bootstrapと[Runtime Bootstrap Contract](docs/architecture/runtime-bootstrap-contract.md) |
| Authority・Route・Context・Runtime・永続化の変更 | [Architecture](docs/architecture/architecture.md)と[Runtime Bootstrap Contract](docs/architecture/runtime-bootstrap-contract.md)の関係する契約 |
| C#・コメント・設計・描画の作業 | `.agents/skills/` の該当Skillと、その変更に必要な `SkillReferences/` |
| Unity Project接続・Capability/Provider解決 | [Local Project Development](docs/local-project-development.md)、[Unity Tool Runtime](Specs/UnityToolRuntime.md) |

Production bootstrapでは、`Orchestration/Routing/task-routes.yaml`からPrimary Routeを一つ選び、選択Routeの `required_policy_clauses` をPolicy provenanceとして記録する。`Context/Selection/context-catalog.yaml`からContext Pack / Primary Skill / Task Contractを解決し、`Context/Assembly/materialize_context.py`でcurrent-call Contextを構築する。Technology keywordだけでRouteを決めない。

bounded Taskは `Policy -> Orchestration Route -> Context -> Runtime -> Verification -> Result` のFast Pathを優先する。semantic coordinationが必要な場合だけParentGraphを使う。Production tool executionはRuntime Tool Broker / Dispatcherを通し、Provider direct dispatchを追加しない。State/Evidenceの永続化・Resume・EvalはRuntime Bootstrap Contractの責務分離に従う。

## Delegation and verification

- Skillの「Delegates to」は責務の委譲先を示す。同じAgentが該当Skillを適用してよく、全候補の読込や別Agent起動を要求しない。
- Subagentはユーザーまたは適用中の指示が明示的に要求し、独立した有益な仕事と実行手段がある場合に使う。対象・変更権限・必要証拠を限定し、同じファイルの並行編集を避ける。結果は統括側が統合・確認する。
- 変更した契約と主張を検証できる最小限のチェックに、Task ContractとCIの必須Gateを加える。UnityAgentのAgent指示変更では `python Tools/validate_all.py` を実行する（依存はCI定義のPyYAML / jsonschema）。
- 必須チェック通過後は、新しい差分・失敗・具体的な未解決Riskがなければ検証を拡張・反復しない。実装の文言をなぞるだけのテストを増やさない。
- Static / Compile / Editor / Player / 実機 / Performance / Visualを区別する。未実行は未実行、環境不足は`unavailable`として報告し、成功を捏造しない。実測のない性能改善、Human reviewのない美的受入を確定しない。

## Completion

日本語で結果を先に述べ、変更理由、検証結果、残る制限、成果物を簡潔に示す。説明の深さ・形式はユーザー指定に合わせる。SkillのOutput contractは必要情報の契約であり、無関係な欄や空欄の大量出力を要求しない。Runtimeの機械可読SchemaとEvidence必須項目は保持する。
