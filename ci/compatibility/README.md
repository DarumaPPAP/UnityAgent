<a id="artist-compatibility-contracts"></a>

# Artistの対応環境と検証状態

[support-matrix.yaml](support-matrix.yaml) がArtist BackendのUnity 6.x+ / Built-in・URP・HDRPの対応対象を宣言する正本です。これは製品の対象宣言であり、実Editorでの検証成功ではありません。Unity 2022.3は現行Production対象外です。

過去のSession、Release監査、受入記録は [Historical Evidence](../../tests/unity/evidence/artist/historical/) に元のバイト列で保存されています。[保存索引](../../tests/unity/evidence/artist/historical/index.json) が元のパス・SHA-256と現在の観測 `not_observed` を記録します。記録内の `passed` は当時の事実です。旧URP/HDRP Fixtureの元パスが基準checkoutにない場合、その記録は現在のFixtureや実行成功を証明しません。

[Archive Validator](../../tests/unity/verify/) は履歴の形式とハッシュを確認します。Unityを起動する検証ではありません。現在のEditor / Pipeline / Capture / Visualは `BLOCKED_NOT_RUN` です。新しい実測Evidenceを `tests/unity/evidence/artist/current/` に記録するには、ライセンス済みEditorでの正確なVersion、ログ、結果、成果物が必要です。

[6000.6 Artist E2E Project](../../tests/unity/projects/artist-e2e/) のSceneとResourceを維持します。[2022.3 Project](../../tests/unity/projects/historical/2022.3/) は履歴用です。使い捨てコピーでのLive確認には、対象を明示したライセンス済み・接続済みEditorが必要です。

```powershell
python -m tools.run_artist_unity_cli_live --project-path <この実行が所有する.artist-e2e~の絶対パス> --camera-name "Main Camera" --output artifacts/artist-live
python -m tools.run_artist_cinematic_live <この実行が所有する.artist-e2e~の絶対パス> artifacts/artist-cinematic
```

これらは変更を伴い得るLive検証で、静的契約検査とは別です。Control Plane → Tool Broker → Unity CLI → Unity Pipeline → Artist UPMを通り、独立Artist Hostは使用しません。文書更新では実行していません。履歴の整合やRegistry登録から実行準備完了を推測せず、ManifestのActivation条件を現在のProjectで独立に観測します。
