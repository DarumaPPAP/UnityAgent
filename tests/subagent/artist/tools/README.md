# 旧Hostの互換Fixture

このディレクトリの `fixtures/` は、旧Hostで使用したUnity 2022.3の最小入力を履歴資料として保持しています。独立Artist Hostとその実行テストは撤去済みです。現在のProduction実行・配布・検証から旧Hostを起動しません。

現行の検証は `tests/runtime/test_artist_*.py`、`tests/subagent/artist/authority/`、`tests/unity/editor/artist/` を使用します。

実Editorの全9コマンドとCinematic Mutationの記録は `tests/unity/evidence/artist/unity-cli-integration/` にあります。歴史Fixtureは現在のEditor成功や性能の証拠として扱いません。
