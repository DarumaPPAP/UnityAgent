"""C0-C8 final completion gate for UnityAgent -> UnityArtist v1.1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
ARTIST_DEFAULT = ROOT.parent / "MyUnityMCP"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 300) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"timeout after {timeout}s\nstdout={str(exc.stdout or '')[-4000:]}\nstderr={str(exc.stderr or '')[-4000:]}"
    except OSError as exc:
        return False, f"could not start command: {exc}"
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output[-6000:]


def _run_json(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 300) -> tuple[int, dict[str, object] | None, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, None, f"timeout after {timeout}s\nstdout={str(exc.stdout or '')[-5000:]}\nstderr={str(exc.stderr or '')[-5000:]}"
    except OSError as exc:
        return 127, None, f"could not start command: {exc}"
    output = (completed.stdout or "").strip()
    try:
        value = json.loads(output) if output else None
    except json.JSONDecodeError:
        value = None
    return completed.returncode, value if isinstance(value, dict) else None, (completed.stdout or "")[-5000:] + (completed.stderr or "")[-5000:]


def _reference_tests(env: dict[str, str]) -> tuple[bool, str]:
    # GoldenArtistTransport is intentionally fixture-only. The real Named Pipe
    # path is exercised by run_camera_fov_reference_live.py below.
    env["UNITYAGENT_RUN_WINDOWS_IPC_TESTS"] = "1"
    env.pop("UNITYAGENT_RUN_GOLDEN_FIXTURE_TESTS", None)
    os.environ["UNITYAGENT_RUN_WINDOWS_IPC_TESTS"] = "1"
    os.environ.pop("UNITYAGENT_RUN_GOLDEN_FIXTURE_TESTS", None)
    suite = unittest.defaultTestLoader.loadTestsFromName("Runtime.Tests.ReferenceImplementation.test_reference_implementation")
    stream = __import__("io").StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    return result.wasSuccessful(), stream.getvalue()


def _namespace_check(artist_root: Path) -> tuple[bool, str]:
    violations: list[str] = []
    roots = [artist_root / "Packages" / "com.darumappap.unity-artist", artist_root / "src" / "UnityArtist.Cli"]
    for root in roots:
        if not root.is_dir():
            violations.append(f"missing namespace root: {root}")
            continue
        for path in root.rglob("*.cs"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "namespace DarumaPPAP.UnityArtist" in text:
                violations.append(str(path))
    return not violations, "namespace UnityArtist check: " + ("PASS" if not violations else "FAIL\n" + "\n".join(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the exact v1.1 final completion gate.")
    parser.add_argument("--unityartist-root", type=Path, default=ARTIST_DEFAULT)
    parser.add_argument("--skip-full-repository", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    env["UNITYAGENT_RUN_WINDOWS_IPC_TESTS"] = "1"
    env.pop("UNITYAGENT_RUN_GOLDEN_FIXTURE_TESTS", None)
    checks: dict[str, object] = {}
    failures: list[str] = []
    external_blockers: list[str] = []

    if args.skip_full_repository:
        checks["unityagent_full_validation"] = "skipped_by_request"
    else:
        ok, output = _run([sys.executable, "Tools/validate_all.py"], cwd=ROOT, env=env, timeout=600)
        checks["unityagent_full_validation"] = {"passed": ok, "tail": output}
        if not ok:
            failures.append("UnityAgent canonical validation")

    ok, output = _reference_tests(env)
    checks["reference_contract_tests"] = {"passed": ok, "tail": output[-6000:]}
    if not ok:
        failures.append("reference implementation contract tests")

    artist_root = args.unityartist_root.resolve()
    namespace_ok, namespace_output = _namespace_check(artist_root)
    checks["unityartist_namespace"] = {"passed": namespace_ok, "detail": namespace_output}
    if not namespace_ok:
        failures.append("UnityArtist namespace migration")

    static_commands = {
        "artist_contract": [sys.executable, "Tests/Release/verify_unity_artist_contract.py"],
        "artist_api_compatibility": [sys.executable, "Tests/Compatibility/verify-unity-api-compatibility.py"],
        "artist_cli_pipeline_gate": [sys.executable, "Tests/Compatibility/verify-cli-pipeline-gate-evidence.py"],
        "artist_2022_bounded_fallback": [sys.executable, "Tests/Compatibility/verify-2022-3-bounded-fallback-evidence.py"],
        "artist_semantic_names": [sys.executable, "Tests/Compatibility/verify-semantic-names.py"],
        "artist_portable_paths": [sys.executable, "Tests/Release/verify_portable_paths.py"],
    }
    for name, command in static_commands.items():
        ok, output = _run(command, cwd=artist_root, env=env, timeout=300)
        checks[name] = {"passed": ok, "tail": output[-4000:]}
        if not ok:
            failures.append(name)

    dotnet_home = artist_root / "Artifacts" / "reference-live" / "dotnet-home"
    nuget = artist_root / "Artifacts" / "reference-live" / "nuget"
    dotnet_home.mkdir(parents=True, exist_ok=True)
    nuget.mkdir(parents=True, exist_ok=True)
    env["DOTNET_CLI_HOME"] = str(dotnet_home)
    env["NUGET_PACKAGES"] = str(nuget)
    env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
    ok, output = _run(["dotnet", "build", "src/UnityArtist.Cli/UnityArtist.Cli.csproj", "--no-restore"], cwd=artist_root, env=env, timeout=300)
    checks["artist_cli_build"] = {"passed": ok, "tail": output[-5000:]}
    if not ok:
        failures.append("UnityArtistCLI build")

    live_command = [sys.executable, str(ROOT / "Tools" / "run_camera_fov_reference_live.py"), "--unityartist-root", str(artist_root)]
    live_code, live_report, live_output = _run_json(live_command, cwd=ROOT, env=env, timeout=900)
    checks["live_unity_control_plane_e2e"] = {"exit_code": live_code, "report": live_report, "tail": live_output[-6000:]}
    if live_report and live_report.get("status") == "blocked_external":
        external_blockers.append("real Unity 6000.6.0f1 E2E: " + str(live_report.get("error")))
    elif live_code != 0 or not live_report or live_report.get("status") != "passed":
        failures.append("real Unity ControlPlane/Named Pipe E2E")

    terminal = "GOAL_COMPLETE"
    if failures:
        terminal = "GOAL_NOT_COMPLETE"
    elif external_blockers:
        terminal = "GOAL_BLOCKED_EXTERNAL"
    report = {
        "terminal": terminal,
        "failures": failures,
        "external_blockers": external_blockers,
        "checks": checks,
        "production_path": "ControlPlane -> ToolBroker -> UnityArtistCLI Provider -> Evidence/Persistence",
        "golden_artist_transport": "fixture_only_excluded_from_final_gate",
    }
    report_path = ROOT / "Artifacts" / "reference-implementation" / "final-completion-gate.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(terminal)
    if terminal == "GOAL_COMPLETE":
        return 0
    if terminal == "GOAL_BLOCKED_EXTERNAL":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
