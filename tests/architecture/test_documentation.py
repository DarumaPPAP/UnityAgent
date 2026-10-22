"""文書検査が参照の破損を検出し、履歴・生成物を誤判定しないことを確認する。"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.documentation_validator import validate_documentation as validator


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(validator, "ROOT", self.root).start()
        patch.object(validator, "MIGRATION_DIR", self.root / "docs/migration").start()
        self.write("README.md", "# 文書\n")
        for relative in validator.REQUIRED_USER_ENTRYPOINTS:
            self.write(relative, "")

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = validator.main()
        return result, output.getvalue()

    def assert_valid(self):
        code, output = self.check()
        self.assertEqual(0, code, output)

    def assert_invalid(self, message):
        code, output = self.check()
        self.assertEqual(1, code, output)
        self.assertIn(message, output)

    def test_existing_repository_without_proposed_pages_remains_valid(self):
        self.assert_valid()

    def test_active_development_and_reference_documents_are_checked(self):
        self.write("docs/development/guide.md", "[missing](absent.md)")
        self.write("docs/references/commands.md", "[missing](absent.md)")
        code, output = self.check()
        self.assertEqual(1, code)
        self.assertIn("docs/development/guide.md", output)
        self.assertIn("docs/references/commands.md", output)

    def test_japanese_duplicate_setext_and_explicit_anchors_are_resolved(self):
        self.write("docs/target.md", "# 日本語と `API`\n## 確認\n## 確認\n補足\n----\n<a id='legacy-id'></a>\n")
        self.write("README.md", "[a](docs/target.md#日本語と-api)\n[b](docs/target.md#確認-1)\n[c](docs/target.md#legacy-id)\n[d](docs/target.md#補足)")
        self.assert_valid()
        self.write("README.md", "[a](docs/target.md#missing)")
        self.assert_invalid("broken markdown anchor")

    def test_html_and_markdown_images_are_checked(self):
        self.write("docs/picture.svg", "<svg/>")
        self.write("README.md", '<img src="docs/picture.svg"/><a href="docs/picture.svg">図</a>\n![図](docs/picture.svg)')
        self.assert_valid()
        self.write("README.md", '<img src="docs/missing.png"/>')
        self.assert_invalid("broken local reference")
        self.write("README.md", "![図](docs/missing.png)")
        self.assert_invalid("broken local reference")

    def test_reference_full_collapsed_shortcut_and_image_links_are_checked(self):
        self.write("docs/target.md", "# 詳細")
        self.write("README.md", "[説明][target]\n[target][]\n[target]\n![画像][picture]\n[target]: docs/target.md#詳細\n[picture]: docs/picture.png")
        self.assert_invalid("docs/picture.png")
        self.write("docs/picture.png", "image")
        self.assert_valid()
        self.write("README.md", "[説明][unknown]")
        self.assert_invalid("undefined markdown reference")

    def test_shortcut_reference_image_destination_is_checked(self):
        self.write("README.md", "![picture]\n\n[picture]: missing.png")
        self.assert_invalid("missing.png")
        self.write("missing.png", "image")
        self.assert_valid()

    def test_image_wrapped_link_checks_both_destinations(self):
        self.write("exists.svg", "<svg/>")
        self.write("README.md", "[![badge](exists.svg)](missing.md)")
        self.assert_invalid("missing.md")
        self.write("missing.md", "# target")
        self.assert_valid()
        self.write("README.md", "[![badge](missing.svg)](missing.md)")
        self.assert_invalid("missing.svg")

    def test_escaped_spaces_parentheses_and_optional_titles_are_resolved(self):
        self.write("docs/file (one).md", "# 詳細")
        self.write("README.md", '[図](<docs/file (one).md#詳細> "説明")\n[図](docs/file%20(one).md#詳細)')
        self.assert_valid()

    def test_fenced_inline_commented_and_external_references_are_ignored(self):
        self.write("README.md", '```md\n[例](missing.md)\n```\n~~~md\n<img src="missing.png">\n~~~\n`[例](missing.md)`\n<!-- [例](missing.md) -->\n[外部](https://example.invalid/a#missing)')
        self.assert_valid()

    def test_percent_encoded_and_symlink_repository_escape_are_rejected(self):
        self.write("README.md", "[escape](%2e%2e/outside.md)")
        self.assert_invalid("escapes repository")
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "outside.md"
            path.write_text("# outside")
            (self.root / "linked.md").symlink_to(path)
            self.write("README.md", "[escape](linked.md)")
            self.assert_invalid("escapes repository")

    def test_generated_and_historical_documents_are_not_current_guides(self):
        for prefix in ("src/unityagent/_resources", "build", "dist", "Artifacts", ".venv", "docs/migration", "docs/development/plans"):
            self.write(f"{prefix}/README.md", "[old](missing.md)")
        self.write("docs/development/unity-setup.md", "[old](missing.md)")
        self.assert_valid()

    def test_new_guides_must_be_reachable_through_real_links(self):
        self.write("docs/getting-started/installation.md", "# 導入")
        self.write("README.md", "`docs/getting-started/installation.md`")
        self.assert_invalid("not reachable from README")
        self.write("README.md", "[文書](docs/README.md)")
        self.write("docs/README.md", "[導入](getting-started/installation.md)")
        self.assert_valid()

    def matrix(self, *, header=None, evidence="[定義](../../source.yaml)", revision="[Commit](https://github.com/DarumaPPAP/UnityAgent/commit/0123456789012345678901234567890123456789)"):
        columns = header or ["機能ID／機能名", "利用条件", "実装状態", "検証状態", "制限", "根拠", "対象Revision"]
        self.write("source.yaml", "kind: example")
        self.write("README.md", "[状態](docs/references/capability-status.md)")
        return self.write("docs/references/capability-status.md", "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n| example | 条件あり | 実装済み | 未観測 | 限定 | " + evidence + " | " + revision + " |\n")

    def test_status_matrix_requires_columns_evidence_and_revision(self):
        self.matrix()
        self.assert_valid()
        self.matrix(header=["機能ID／機能名", "利用条件", "実装状態", "検証状態", "制限", "根拠"])
        self.assert_invalid("required status columns")
        self.matrix(evidence="テストがある")
        self.assert_invalid("status evidence must contain a link")
        self.matrix(revision="")
        self.assert_invalid("empty status field")

    def test_empty_status_matrix_is_rejected(self):
        self.write("README.md", "[状態](docs/references/capability-status.md)")
        self.write("docs/references/capability-status.md", "# 状態\n後で記入")
        self.assert_invalid("required status columns")


    def test_status_matrix_revision_requires_linked_full_commit(self):
        self.matrix()
        self.assert_valid()
        self.matrix(revision="unknown")
        self.assert_invalid("status revision must link")
        self.matrix(revision="[Commit](https://github.com/DarumaPPAP/UnityAgent/commit/short)")
        self.assert_invalid("status revision must link")

    def test_tool_capability_rows_must_match_canonical_schema(self):
        self.write(
            validator.CAPABILITY_SCHEMA,
            "properties:\n  capability:\n    enum: [project.inspect, source.read]\n",
        )
        self.write("README.md", "[状態](docs/references/capability-status.md)")
        revision = "[Commit](https://github.com/DarumaPPAP/UnityAgent/commit/0123456789012345678901234567890123456789)"
        def matrix(ids):
            rows = "".join(
                f"| \`{cap}\` | 条件 | 実装済み | 未観測 | 制限 | [定義](../../source.yaml) | {revision} |\n"
                for cap in ids
            )
            self.write("source.yaml", "kind: example")
            self.write(
                "docs/references/capability-status.md",
                "## Tool Capability\n\n"
                "| 機能ID／機能名 | 利用条件 | 実装状態 | 検証状態 | 制限 | 根拠 | 対象Revision |\n"
                "|---|---|---|---|---|---|---|\n" + rows,
            )
        matrix(["project.inspect", "source.read"])
        self.assert_valid()
        matrix(["project.inspect"])
        self.assert_invalid("tool capability matrix differs from schema")
        matrix(["project.inspect", "source.read", "unexpected.capability"])
        self.assert_invalid("tool capability matrix differs from schema")
        matrix(["project.inspect", "source.read", "source.read"])
        self.assert_invalid("duplicate tool capability")


if __name__ == "__main__":
    unittest.main()
