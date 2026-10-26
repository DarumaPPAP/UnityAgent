# Artist Unity CLI最終Evidence

固定Revisionは85bcfb4cd41e89efaf63c8345fe36ae7162bda08。index.jsonを入口に、liveの各summary、matrixのXML／Package lock／GPU readback、verificationのBaseline比較とCI、developmentのHashを確認する。

`durable-evidence.zip` は155件の永続Evidence、イベント、Provider結果・Context manifest、Capture画像を含む。内部file-hashes.jsonを全entryと照合済み。認証情報は収録しない。絶対パスは実行時の所有Fixtureを示す観測値であり、他環境で同じパスを使う契約ではない。

再実行はRepository正本の tools/run_artist_unity_cli_live.py、tools/run_artist_cinematic_live.py、tests/unity/verify/unity_ci.py を使用する。各runnerの --help と専用Fixture前提を確認し、本番Projectを代用しない。Windowsの既存失敗はverification/baseline-comparison.jsonを参照。過去のEvidenceを新しいコードの成功証拠として使わない。
