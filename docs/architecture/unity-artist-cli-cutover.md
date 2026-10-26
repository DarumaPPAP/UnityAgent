# Artist実行Backend移行の互換記録

以前の `unity_artist_cli` を専門Agentや実行Backendとして選出する中間モデルは、現行契約ではありません。現在の正本は [ArtistSubAgent境界](artist-subagent-boundary.md) です。

- 専門Agentの正本IDは `artist_subagent` / `ArtistSubAgent`、実行Providerは `unity_cli` です。全9コマンドを対象ProjectのUnity PipelineとArtist UPMで実行します。
- `unity_artist_cli` は過去のSnapshot／InstallReceiptの読取互換に限定します。新規Provider登録・Setup・Fallbackには使用せず、独立Artist Hostを導入・起動しません。
- ArtistSubAgentは任意導入です。現在のProjectの `artist.compatible`、Package、binding、Pipeline到達性を三値で観測し、必須Factがfalse／unknownなら選出しません。
- 要求充足のための自動Installは行いません。UnityAgent Control Planeが唯一のEntry・Policy／Approval境界を維持します。

過去の実装はGit履歴と監査記録で参照できます。旧Provider名を現在の実行経路へ戻さないでください。
