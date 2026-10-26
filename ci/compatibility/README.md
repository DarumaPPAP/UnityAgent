<a id="artist-compatibility-contracts"></a>

# Artistの対応環境と検証状態

[support-matrix.yaml](support-matrix.yaml) がArtist BackendのUnity 6.x+ / Built-in・URP・HDRPの対応対象を宣言する正本です。これは製品の対象宣言であり、実Editorでの検証成功ではありません。Unity 2022.3は現行Production対象外です。


[Archive Validator](../../tests/unity/verify/) は履歴の形式とハッシュを確認します。Unityを起動する検証ではありません。現在のEditor / Pipeline / Capture / Visualは `BLOCKED_NOT_RUN` です。新しい実測Evidenceを `tests/unity/evidence/artist/current/` に記録するには、ライセンス済みEditorでの正確なVersion、ログ、結果、成果物が必要です。


```powershell
python -m tools.run_artist_unity_cli_live --project-path <この実行が所有する.artist-e2e~の絶対パス> --camera-name "Main Camera" --output artifacts/artist-live
python -m tools.run_artist_cinematic_live <この実行が所有する.artist-e2e~の絶対パス> artifacts/artist-cinematic
```

これらは変更を伴い得るLive検証で、静的契約検査とは別です。Control Plane → Tool Broker → Unity CLI → Unity Pipeline → Artist UPMを通り、独立Artist Hostは使用しません。文書更新では実行していません。履歴の整合やRegistry登録から実行準備完了を推測せず、ManifestのActivation条件を現在のProjectで独立に観測します。
