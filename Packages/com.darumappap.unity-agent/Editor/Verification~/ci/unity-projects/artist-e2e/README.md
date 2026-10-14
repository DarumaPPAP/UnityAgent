# Artist Backend Project Detection Fixture

このFixtureは、Host CLIのUnity Project検出とPackage Path解決を確認する最小Unity Projectです。これ単体ではEditor / PipelineのLive CompatibilityやArtistSubAgent Resolver eligibilityを証明しません。

Direct Editor / Pipeline Testでは、同じArtist Packageを正式Support Matrixから選んだUnity VersionとPipelineに接続して使います。Version別の結果は`Tests/Compatibility/`のEvidenceを参照してください。
