# Unity 2022.3 Official Pipeline Gate Fixture

この最小Built-in Unity Projectは、Artist BackendのCompatibility検証でOfficial Unity CLI / Pipelineの初回候補を試すDisposable Fixtureです。Unity 2022.3向けの対応機能を示すDemoではありません。

この環境では、列挙済みOfficial Pipeline VersionがUnity 6.0以上を要求し、Editor接続前に失敗したことを記録しています。結果は`Tests/Compatibility/cli-pipeline-gate-evidence.yaml`に保存されています。明示的なGate FailureのEvidenceと別途承認されたContractがない限り、Fallback Backendへ切り替えません。

このFixtureにはArtistによるScene Authoringを追加しません。
