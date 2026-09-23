# UnityAgent / UnitySubAgentHub Integration Architecture Audit

対象: UnityAgent `34c5911`、UnitySubAgentHub `c85d451`（いずれも監査開始時のmain）。この文書はCatalog/Registryの所有権を変更せず、境界を横断する参照とSetup入口を監査した記録である。

## Entry point inventory

| Entry | Repository | Type / Owner | Required / Optional | Current status / Reference / Evidence |
|---|---|---|---|---|
| `unity-agent` | UnityAgent | Host CLI / Control Plane | Integration時に必要 | Active。`Tools/unity_agent_cli.py` → `UnityAgentControlPlane.setup` → `ToolBroker.dispatch_management` |
| `unity-agent` Codex Plugin | UnityAgent | Plugin / Entry | Optional | Active。`.agents/plugins/unity-agent/.codex-plugin/plugin.json`、Setup Skill |
| `com.darumappap.unity-agent` | UnityAgent | UPM / Unity UI Entry | Optional | Active。`UnityAgentSetupWindow.cs` → `UnityAgentControlPlaneClient.cs` |
| Official Unity CLI | UnityAgent | Backend Provider | Optional | Active if observed。`Runtime/Tooling/provider_registry.yaml`、`unity_cli_provider.py` |
| File / native Editor / MCP / Player | UnityAgent | Backend Providers | Optional | FactとRegistry次第。`Runtime/Tooling/provider_registry.yaml`。`myunitymcp`はproduction-disabled |
| `unity-artist` | UnitySubAgentHub | Artist Backend CLI | Optional | Active Backend。`src/UnityArtist.Cli/`。UnityAgent連携のSetup/Approval入口ではない |
| `com.darumappap.unity-artist` | UnitySubAgentHub | Artist Backend UPM | Optional | Active Backend。`SubAgents/artist_subagent/manifest.yaml`でdependency宣言 |
| `artist_subagent` | UnitySubAgentHub → UnityAgent | Manifest / imported profile | Optional | Hub Manifest → Snapshot → UnityAgent checked-in Catalog。自動同期なし。false/unknownのActivation Gateでは除外 |

## Issue report

以下の各項目は `Issue / Repository / Location / Evidence / Current / Expected / Root Cause / Impact / Action / Priority` を順に示す。`Fix Now` はこの監査の変更対象、`Issue` は別の判断または実環境が必要、`Keep` は意図的な互換・履歴である。

1. **旧bootstrap入口** — UnityAgent / `.agents/plugins/unity-agent/skills/unity-agent-setup/SKILL.md`。Evidence: 旧移行ブランチの`install-remote.ps1`と`UNITY_AGENT_REF`を案内していた。Current: Skillと現行`README.md`/`scripts/install.ps1`が不一致。Expected: mainの`install.ps1`、`UNITY_AGENT_TAG`、隔離されたvenvの説明。Root Cause: bootstrap移行後のSkill更新漏れ。Impact: 初回導入失敗、異なるVersionの導入。Action: 現行入口へ更新しArchitectureテスト追加。Priority: P1 / Fix Now。
2. **Backend Release配布元が旧Repository** — UnityAgent / `Runtime/Tooling/Providers/Installer/release_installer.py`。Evidence: `REPOSITORY`が旧名、Hubの`v0.0.1-beta` Releaseにはhost ZIPとSHA-256 sidecarがある。Current: Setup Applyが旧URLへアクセス。Expected: `DarumaPPAP/UnitySubAgentHub`の固定Release。Root Cause: Repository Rename後のruntime参照更新漏れ。Impact: redirect依存、将来のInstall失敗。Action: 固定配布元を更新し要求URLをテスト。Priority: P1 / Fix Now。
3. **LookDev Contextの旧参照** — UnityAgent / `Context/Packs/artist-lookdev.yaml`。Evidence: 旧Repositoryの`Specs/UnityArtistCLI/spec.md`を指す一方、Hub現行正本は`Specs/ArtistSubAgent/spec.md`。Current: Context取得で旧仕様へ誘導。Expected: Hubの現行Spec。Root Cause: Context Pack移行漏れ。Impact: 誤った設計判断。Action: 参照先を更新。Priority: P1 / Fix Now。
4. **Cinematic Contextの旧参照** — UnityAgent / `Context/Packs/artist-cinematic.yaml`。Evidence: 上記と同じ旧Spec参照が独立した必須Contextに残存。Current: Cinematic要求に旧仕様を注入。Expected: Hubの現行Spec。Root Cause: 別Packの移行漏れ。Impact: Artist境界と操作前提の誤認。Action: 参照先を更新。Priority: P1 / Fix Now。
5. **Hub SkillがBackendを直接Install** — UnitySubAgentHub / `.agents/skills/artist-subagent-backend-setup/SKILL.md`。Evidence: 旧手順が`unity artist install`をSetup入口として提示。Current: UnityAgent Setup PlanとApprovalを経由しない案内。Expected: `unity-agent doctor → setup plan → approval → setup apply → doctor`。Root Cause: Control Plane導入前のSkill手順。Impact: Scope/Receipt/Evidence契約の迂回。Action: UnityAgent入口へ修正し回帰テスト追加。Priority: P1 / Fix Now。
6. **Hub Artist Guideの旧Catalog説明** — UnitySubAgentHub / `SubAgents/artist_subagent/README.md`。Evidence: `unity_artist_cli` Profile、Activation差分でImport不能と記載。Current: 実際には`artist_subagent` CatalogとOffline Import Gateがある。Expected: 明示的Import、同期なし、実環境Gateを説明。Root Cause: Import Gate導入後のGuide更新漏れ。Impact: 利用者が現行Resolverを使えないと誤認。Action: 現行契約へ更新。Priority: P1 / Fix Now。
7. **Package説明のSetup入口が曖昧** — UnitySubAgentHub / `Packages/com.darumappap.unity-artist/Documentation~/README.md`。Evidence: Host CLI節で`unity artist install`を直接提示。Current: Backend CommandとIntegration Setupが混在。Expected: UnityAgentの承認付きSetupを明記し、Backend操作面と区別。Root Cause: Package単独の旧説明。Impact: 誤導入。Action: 説明を補正。Priority: P2 / Fix Now。
8. **Hub Setup説明がCI対象外** — UnitySubAgentHub / `.github/workflows/subagent-hub-contract.yml`。Evidence: Skill / README / Packageドキュメント変更ではHub Contractが起動しなかった。Current: Setup導線のRegression検出が遅れる。Expected: それらをpath filterに含める。Root Cause: Governanceファイル追加後のCI追随漏れ。Impact: 旧手順再混入。Action: Filterとテストを更新。Priority: P2 / Fix Now。
9. **ローカル開発ガイドの所有権図** — UnityAgent / `docs/local-project-development.md`。Evidence: Artist Capability Schemaの所有者をUnityArtistCLIと説明。Current: Hub Manifestの所有者が図に登場しない。Expected: HubがManifest/Contract、Backendが実行。Root Cause: Hub分離前のDocumentation。Impact: 契約変更を誤ったRepositoryで行う。Action: 所有権図と箇条書きを修正。Priority: P2 / Fix Now。
10. **旧MCPの候補表示** — UnityAgent / `Specs/UnityEnvironmentCapabilityMatrix.yaml`。Evidence: `production_runtime_authority: false`の補助Matrixに`myunitymcp`を`likely_candidates`として記載する一方、Registryはproduction-disabled。Current: 補助資料だけ読むと選択可能に見える。Expected: 実行候補はRegistry/Factsで判定すると明示し、Matrix更新可否を別途判断。Root Cause: 以前のProvider対応表。Impact: 読者の誤判断。Action: MCP全体の移行範囲・外部利用を確認するIssueで扱う。Priority: P2 / Issue。
11. **過去のインストーラーURL** — UnitySubAgentHub / `Design/DecisionLog/2026-09-11-remote-bootstrap-installer.md`。Evidence: 旧Repository名の当時の決定を記録。Current: History。Expected: 当時の判断を再現できること。Root Cause: 意図的な履歴。Impact: 現行入口として引用すると誤解。Action: 改変せず現行Skill/Guideを参照。Priority: P3 / Keep。
12. **Catalogの同期とLive実行は未実証** — Both / Hub `Tests/Hub/export_agent_snapshot.py`、UnityAgent `Tools/import_subagent_catalog.py`、Unity Editor。Evidence: この監査で実SnapshotのOffline Import Planは`no_op`、静的Contractは通過。Current: Artifact自動同期とUnity ProjectでのPlugin→Artist実行は未観測。Expected: 次回Integration TestでPlugin/ArtistのActivation Facts、Approval、Evidenceを実測。Root Cause: 本監査の環境にUnity Editor/対象Project/Pluginがない。Impact: 実行準備完了の主張は不可。Action: Integration Test Part 2で検証。Priority: P1 / Issue。

## Cross-repository contract and validation

`artist_subagent`はProfile ID、`unity_artist_cli`はProvider ID。Hub ManifestとUnityAgent Catalogの`schema_version`、capabilities、activation、producer `UnityAgent.ReferenceImplementation.v1.1`は一致した。Hub ExporterのYAML bytesは表記差によりCatalogと異なるが、UnityAgentのOffline Import Gateは検証のうえ`no_op`を返した。SHA-256とsource_refは実際のSnapshot bytesに紐付けた。Hub Registryは実行、解決、導入を所有しない。

| Command | Result / Evidence |
|---|---|
| `python Tools/validate_all.py` (UnityAgent) | 全Validatorとunittest suite通過。Catalog、Layer、Provider、Documentation、Context、Setupを含む |
| `python Tests/Hub/validate_registry.py` | `0 error(s)` |
| `python -m unittest discover -s Tests/Hub -p 'test_*.py' -v` | 20 tests、OK |
| `python Tests/Hub/export_agent_snapshot.py --output /tmp/unityagent-hub-audit-after.yaml` | Active ManifestからSnapshot生成 |
| `python Tools/import_subagent_catalog.py --snapshot ... --source-ref ... --expected-sha256 ... --format json` | `status: no_op`, strict schema/semantic passed, apply read-only |
| `python Tests/Release/verify_unity_artist_contract.py` | `0 error(s)`（tag fetch後） |
| `python Tests/Compatibility/verify-unity-api-compatibility.py` | static contract PASS |
| `python Tests/Release/verify_portable_paths.py` / `verify_remote_installer_contract.py` | PASS |

## Decision

Integration Architecture Status: **Needs Cleanup**。静的境界とCatalog契約は整合したが、Unity Project上のCodex Plugin + Artist実行経路、実環境Gate、InstallReceipt、Evidenceは未観測。UnityAgent Status: 静的検証通過、Live統合未検証。UnitySubAgentHub Status: Registry/Snapshot/Backend静的検証通過、Live統合未検証。次の作業は、現行PluginとArtist Backendを明示的Setupで導入した対象Projectでdoctor/plan/approval/apply/verifyと`artist.camera.inspect`/`artist.camera.refine`のEvidenceを確認すること。
