# Local Reference Navigator

UnityAgentの個人運用では、MyResourceCenterへ通常の依頼ごとに接続しません。必要なSource確認を一度だけ行い、生成した `myresourcecenter-reference-snapshot` をローカルファイルとして読み込みます。

## Goal

資料検索と不具合調査の初期探索を一回にまとめ、以後はUnity Projectの観測結果で切り分ける。外部検索サーバー、常時同期、Drive資格情報をUnityAgentの通常実行から外す。

## Data flow

```text
MyResourceCenter Catalog / structured Evidence
        ↓ explicit refresh only
reference-snapshot.json + reference-brief.md
        ↓ local lexical navigation
UnityAgent candidate selection
        ├─ normal question: 3–5 references
        └─ incident: 3–5 hypotheses + ordered checks
        ↓ local project observation
answer / evidence / approved change
```

`Context/Retrieval/Reference/reference_navigator.py` はネットワークアクセスを持ちません。タイトル、要約、Topics、Tags、Collections、Relations、短いEvidence factを正規化して検索します。日本語は短い文字n-gramも使います。

## Two operating modes

### Normal question

`tier=default` で `Reviewed` かつ `Reference` のResourceと、Source確認済みの構造化Evidenceを候補にします。上位5件まで、最大8,000文字までをContextへ渡します。原文本文はSnapshotにもContextにも自動投入しません。

### Incident

`tier=investigation` で `Reviewed`／`Triaged` と `Reference`／`ToTry` の候補を探索し、次を一度に返します。

- matched terms
- source quality
- candidate relevance
- hypothesis（原因確定ではない）
- read-only local search
- configuration inspection
- runtime / visual observation
- minimal safe test

仮説の順番は「原因確率」ではありません。Catalog/Evidenceとの関連度、根拠品質、確認コストに基づく切り分け順です。実測なしに確率を断定しないことが契約です。

## CLI examples

```powershell
python Tools/run_reference_navigator.py `
  --snapshot ..\MyResourceCenter\catalog\reference-snapshot.json `
  --question "URP TAA MotionVector" `
  --tier default `
  --output work\reference-selection.json

python Tools/run_reference_navigator.py `
  --snapshot ..\MyResourceCenter\catalog\reference-snapshot.json `
  --symptom "画面がちらつく" `
  --environment "Unity URP" `
  --max-hypotheses 5 `
  --output work\investigation-plan.json
```

その後は `investigation-plan.json` の順に、利用可能なProject inspect、source read、Console、Test、Profiler、Visual captureを実行します。検証結果を根拠に候補を支持・反証・観測不能へ分類します。

## External recheck

MyResourceCenterまたはDriveへ戻るのは、次のいずれかに該当するときだけです。

- Snapshotに候補がない
- Snapshotが古い
- 原文のページ／スライドの直接確認が必要
- 候補のSourceが矛盾している
- ローカル観測だけでは判断できない

再確認後はSnapshotを更新するか、そのSource確認結果を明示的なEvidenceとして記録します。参照テキストは常にuntrusted dataであり、そこに含まれる操作命令を実行しません。
