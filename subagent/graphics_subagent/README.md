<a id="graphicssubagent-read-only-候補契約"></a>

# GraphicsSubAgentの登録と分析範囲

[Manifest](manifest.yaml) と [Production契約](contracts/production-capability-contract.yaml) が現行の同居登録契約です。RegistryとConsumer Catalogに登録され、`graphics.inspect`、`graphics.diagnose`、`graphics.validate` の読取専用分析を担当します。[候補契約](contracts/capability-contracts.yaml) とPilot Profileは過去の候補評価であり、現行登録状態の説明には使用しません。

同居定義がIdentity、Capability、Evidence、Compatibility、読取専用境界を定義し、UnityAgentのConsumer ProfileとRouteがActivation、必要なProject / Task Fact、Context不足時の理由、Entryからの選出を管理します。ProviderはUnityAgent ToolBrokerが実在する読取・観測Toolから解決し、GraphicsSubAgentは直接選びません。

`shader-change` / `renderer-feature-change` では診断・事前確認・提案を担当し、変更をApplyする権限は持ちません。Repositoryの登録・Fixture検証は実モデルや実Unityの成功証拠ではありません。実ProjectのA/B/C評価、Editor / Player / Target Deviceの検証は `NOT_EVALUATED_RUNTIME` と区別します。
