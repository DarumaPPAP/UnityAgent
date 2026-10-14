# SubAgent統合実行の移行仕様

会話で合意した設計と「移行してください」の実装要求に基づく。
UnityAgentを唯一のControl Planeとし、`subagent/` に同居した4定義を使用する。
Mode UIは設けない。Artistの公開ID、CLI名、Package GUIDとoptional installを維持する。

## 今回接続する境界

- ReleaseのArtist CLI、UPM、Catalog、RegistryはUnityAgentの同じcheckoutから生成する。
  旧Hub Pinは履歴互換検証用に残し、Releaseの取得源には使用しない。
- Python wheelとsdistにSubAgent定義・共有Schema・Instructions・Contractsを含める。
  既存resource-manifestで同梱bytesを検証する。
- Entry v2に任意の`requested_subagent`を追加する。Routeが決めた担当と一致する場合のみ
  既存activation/context gateへ進む。非互換・未導入の指定は拒否し、Backend指定へ転用しない。
- Control PlaneがAdaptive経路を選択し、Orchestration decisionへ永続化する。
  小規模なproject inspectionはFast。単一専門TaskはStandard。
  複数Task DAGは既存plannerを維持し、新たな並列実行を無検証で有効化しない。
- 同じ物理ProjectへのControl Plane実行は同じHost/OSユーザーで共有するOS file lockで排他する。
  ロックは処理・検証・Evidence永続化まで保持する。競合時はBLOCKEDを返す。
  期限切れだけで奪取しない。OS所有権が解放されるまで再取得不可。
  このロックはユーザー手動操作・非協調プロセスを制御しない。

## 維持するGateと未観測

Approval、Project binding、Context ID/Fingerprint、Scope、Evidenceを迂回しない。
Graphics/Performanceのread-onlyとWorldCreatorのplanning-only契約を、コード編集能力の
実装・実Editor検証なしで変更しない。現行Entryの診断/計画成功をゲーム実装E2E完了と混同しない。
Unity Editor/Console環境がない場合は実検証をnot_observedと記録する。
Hub Archive・Release・Mergeは別の明示操作であり、このPRでは実施しない。

## 受入

既存validate_all、Release旧Hub checkout非依存、wheel/sdist抽出検証、
同一Project別プロセス競合・symlink alias・例外後解放、明示指定の一致/不一致、
Control PlaneのFast/Standard decision保存を検証する。
