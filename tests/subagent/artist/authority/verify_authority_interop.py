"""実 C# guard と実 Python Control Plane の署名・単回承認相互接続を検証する。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from tests.runtime.test_artist_authority import ArtistAuthorityTests


ROOT = Path(__file__).resolve().parents[4]
PROJECT = Path(__file__).with_name("AuthorityClientTests.csproj")
ASSEMBLY = Path(__file__).parent / "bin/Debug/net8.0/AuthorityClientTests.dll"


def main() -> None:
    subprocess.run(["dotnet", "build", str(PROJECT), "--nologo", "--verbosity", "quiet"], check=True, cwd=ROOT)
    fixture = ArtistAuthorityTests()
    fixture.setUp()
    try:
        authority = fixture.authority()
        with tempfile.TemporaryDirectory(prefix="artist-authority-interop-") as temp:
            request_path = Path(temp) / "request.json"
            with authority:
                request_path.write_text(json.dumps(fixture.request(authority)), encoding="utf-8")
                for expected in (True, False):
                    result = subprocess.run(["dotnet", str(ASSEMBLY), "--live", str(request_path)], check=False, capture_output=True, text=True, timeout=15, cwd=ROOT)
                    response = json.loads(result.stdout)
                    assert response["allowed"] is expected, response
                    assert result.returncode == (0 if expected else 2), result.stderr
                    if expected:
                        assert response["authorityReservationId"]
        print("PASS: real C# guard -> real Python authority, authenticated response, durable replay denial")
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
