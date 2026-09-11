from __future__ import annotations

import hashlib
import io
import shutil
import sys
import unittest
import uuid
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Runtime.Tooling.Providers.Installer.release_installer import ReleaseInstallError, install_plan


class InstallerProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.install_root = ROOT / f".tmp-installer-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.install_root, ignore_errors=True))

    @staticmethod
    def archive(*, unsafe: bool = False) -> bytes:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("payload/unity-artist.exe", b"UnityArtistCLI beta test payload")
            if unsafe:
                package.writestr("../escape.txt", b"must not extract")
        return stream.getvalue()

    def test_release_archive_is_hash_verified_and_installed_to_requested_root(self) -> None:
        archive = self.archive()
        digest = hashlib.sha256(archive).hexdigest()
        urls: list[str] = []

        def download(url: str) -> bytes:
            urls.append(url)
            return archive if url.endswith(".zip") else f"{digest}  archive.zip\n".encode("utf-8")

        result = install_plan(
            {
                "project_root": str(ROOT),
                "plan_id": "plan-test",
                "install_root": str(self.install_root),
                "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
            },
            download_fn=download,
        )
        self.assertEqual(result["status"], "passed")
        self.assertTrue((self.install_root / "unity-artist.exe").is_file())
        self.assertEqual(result["install_receipt"]["entries"][0]["sha256"], f"sha256:{digest}")
        self.assertEqual(len(urls), 2)

    def test_archive_path_escape_is_rejected(self) -> None:
        archive = self.archive(unsafe=True)
        digest = hashlib.sha256(archive).hexdigest()

        def download(url: str) -> bytes:
            return archive if url.endswith(".zip") else f"{digest}\n".encode("utf-8")

        with self.assertRaises(ReleaseInstallError):
            install_plan(
                {
                    "project_root": str(ROOT),
                    "plan_id": "plan-unsafe",
                    "install_root": str(self.install_root),
                    "actions": [{"product": "unity_artist_cli", "action": "install_then_verify"}],
                },
                download_fn=download,
            )


if __name__ == "__main__":
    unittest.main()
