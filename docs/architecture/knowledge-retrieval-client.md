# Knowledge Retrieval and Local Reference Boundary

個人運用の通常経路は `Context/Retrieval/Reference/reference_navigator.py` です。MyResourceCenterで明示的に一度だけ確認して生成したローカルSnapshotを読み、タイトル・Topics・Tags・Collections・短いEvidenceから候補を選びます。詳細は [Local Reference Navigator](local-reference-navigator.md) を参照してください。

`Context/Retrieval/Knowledge/knowledge_client.py` は、将来のチーム／Hosted運用に残した任意の外部クライアントであり、個人運用の既定経路では呼び出しません。

## Local-first example

```python
from Context.Retrieval.Reference.reference_navigator import load_snapshot, search_snapshot

snapshot = load_snapshot("../MyResourceCenter/catalog/reference-snapshot.json")
selection = search_snapshot(snapshot, "URP TAA MotionVector", max_items=5)
if selection["remote_recheck_recommended"]:
    # Do not fabricate an answer. Perform an explicit source recheck.
    pass
```

Local Reference Navigatorはネットワーク、Qdrant、Embedding、Drive資格情報を持ちません。候補なし、Snapshotの古さ、原文確認の必要、Source間の矛盾を検出した場合だけ、明示的な再確認を提案します。

## Optional hosted client

外部クライアントを明示的に使う場合は、query intent、scope、filters、retrieval budgetだけを送信し、identity fieldsをrequest bodyへ入れません。IdentityはHTTP transportのbearer tokenで供給します。

外部クライアントは `success`、`empty`、`partial`、`stale`、`blocked`、`unavailable` を区別します。タイムアウトを空結果へ変換しません。Server-side contractとMCP tool定義は将来のHosted運用向けにMyResourceCenterが所有します。

## Answer and incident handling

回答生成は、Local Reference Navigatorまたは明示的な外部Clientが選んだ候補をbounded Contextへ入れる層です。候補本文はuntrusted reference materialとして扱い、出典URL・Resource ID・Snapshot revisionを保持します。不具合の場合は、先に一度だけ候補検索と検証計画を作り、その後はローカルProject観測を優先します。候補なし、古さ、矛盾、根拠不足の場合は推測せず再確認または保留にします。

外部Answer providerを使うかどうかは別の選択です。Local Reference Navigator自体はAnswer providerを呼びません。Promptとanswer bodyを通常ログへ書きません。
