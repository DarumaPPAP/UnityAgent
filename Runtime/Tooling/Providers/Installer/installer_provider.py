"""Bounded Installer Provider for the UnityAgent Control Plane.

The adapter owns toolchain observation and approved installation mechanics. It is
never called by Entry directly; ToolBroker management dispatch is the only route.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping, Sequence

from Runtime.Contracts.toolchain_setup_contract import validate_toolchain_setup_request
from Runtime.Tooling.Providers.Installer.codex_plugin_installer import (
    CommandRunner,
    CodexPluginInstallError,
    observe_codex_plugin,
    run_command,
)
from Runtime.Tooling.Providers.Installer.release_installer import ReleaseInstallError
from Runtime.Tooling.Providers.Installer.toolchain_installer import install_toolchain_plan

PRODUCTS = frozenset({
    "official_unity_cli",
    "unity_artist_cli",
    "codex_cli",
    "unity_agent_codex_plugin",
})
PACKAGE_IDS = ("com.unity-artist", "com.darumappap.unity-artist")
CHANNEL = "0.0.4-beta"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _package_version(project_root: Path) -> tuple[str | None, str | None]:
    manifest = project_root / "Packages/manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, None
    dependencies = value.get("dependencies") if isinstance(value, dict) else None
    if not isinstance(dependencies, dict):
        return None, None
    for package_id in PACKAGE_IDS:
        version = dependencies.get(package_id)
        if isinstance(version, str) and version.strip():
            return package_id, version
    return None, None


def _plan_id(project_root: str, products: Sequence[str], report: Mapping[str, Any]) -> str:
    material = json.dumps(
        {"project_root": str(Path(project_root).resolve()), "products": list(products), "report": report},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "plan-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _candidate_codex_paths(env: Mapping[str, str]) -> list[tuple[Path, str]]:
    direct: list[tuple[Path, str]] = []
    for key in ("UNITY_AGENT_CODEX_CLI", "CODEX_CLI"):
        value = env.get(key)
        if value:
            direct.append((Path(value).expanduser(), f"environment:{key}"))

    roots: list[tuple[Path, str]] = []
    npm_prefix = env.get("NPM_CONFIG_PREFIX")
    if npm_prefix:
        prefix = Path(npm_prefix).expanduser()
        roots.extend([(prefix, "npm_prefix"), (prefix / "bin", "npm_prefix")])

    app_data = env.get("APPDATA")
    if app_data:
        roots.append((Path(app_data).expanduser() / "npm", "windows_npm"))

    local_app_data = env.get("LOCALAPPDATA")
    if local_app_data:
        local = Path(local_app_data).expanduser()
        roots.extend([
            (local / "npm", "windows_npm"),
            (local / "Programs/codex", "windows_native"),
            (local / "Programs/nodejs", "windows_node"),
        ])

    program_files = env.get("ProgramFiles") or env.get("PROGRAMFILES")
    if program_files:
        roots.append((Path(program_files).expanduser() / "nodejs", "windows_node"))

    nvm_symlink = env.get("NVM_SYMLINK")
    if nvm_symlink:
        roots.append((Path(nvm_symlink).expanduser(), "nvm_symlink"))

    user_profile = env.get("USERPROFILE") or env.get("HOME")
    if user_profile:
        home = Path(user_profile).expanduser()
        roots.extend([
            (home / "AppData/Roaming/npm", "windows_npm"),
            (home / "AppData/Local/npm", "windows_npm"),
            (home / ".local/bin", "user_local"),
            (home / ".npm-global/bin", "npm_global"),
        ])
        nvm_root = home / ".nvm/versions/node"
        if nvm_root.is_dir():
            for version_dir in sorted(nvm_root.iterdir(), reverse=True):
                if version_dir.is_dir():
                    roots.append((version_dir / "bin", "nvm"))

    seen: set[str] = set()
    candidates: list[tuple[Path, str]] = []
    for candidate, source in direct:
        key = str(candidate).casefold()
        if key not in seen:
            seen.add(key)
            candidates.append((candidate, source))
    for root, source in roots:
        for filename in ("codex.cmd", "codex.exe", "codex.bat", "codex.ps1", "codex"):
            candidate = root / filename
            key = str(candidate).casefold()
            if key not in seen:
                seen.add(key)
                candidates.append((candidate, source))
    return candidates


class InstallerProvider:
    """Management Provider selected through the existing Runtime registry."""

    provider_id = "installer"
    operations = frozenset({"doctor", "plan", "apply"})

    def __init__(
        self,
        project_root: str | Path,
        *,
        which_fn: Callable[[str], str | None] = shutil.which,
        command_runner: CommandRunner = run_command,
        installer_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve(strict=False)
        self.which_fn = which_fn
        self.command_runner = command_runner
        self.env = dict(os.environ if env is None else env)
        self.installer_fn = installer_fn or (
            lambda plan: install_toolchain_plan(
                plan,
                which_fn=self.which_fn,
                command_runner=self.command_runner,
            )
        )

    def _resolve_codex_cli(self, requested_path: object | None) -> tuple[str | None, str, str | None]:
        if requested_path:
            candidate = Path(str(requested_path)).expanduser().resolve(strict=False)
            if candidate.is_file():
                return str(candidate), "explicit_override", None
            return None, "explicit_override", "codex_cli_override_missing"

        detected = self.which_fn("codex")
        if detected:
            return str(detected), "PATH", None

        for candidate, source in _candidate_codex_paths(self.env):
            if candidate.is_file():
                return str(candidate.resolve(strict=False)), source, None

        return None, "auto_detect", "codex_cli_unavailable"

    def _observe_codex_cli(self, request: Mapping[str, Any]) -> dict[str, Any]:
        codex_path, codex_source, codex_reason = self._resolve_codex_cli(request.get("codex_cli_path"))
        if not codex_path:
            return {
                "product": "codex_cli",
                "status": "unavailable",
                "version": None,
                "location": None,
                "source": codex_source,
                "sha256": None,
                "reason": codex_reason,
                "message": "Codex CLI was not found in the selected path, inherited PATH, or common install locations.",
            }

        try:
            result = self.command_runner([codex_path, "--version"])
        except CodexPluginInstallError as exc:
            return {
                "product": "codex_cli",
                "status": "failed",
                "version": None,
                "location": codex_path,
                "source": codex_source,
                "sha256": None,
                "reason": "codex_cli_execution_failed",
                "message": str(exc),
            }

        version_text = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return {
                "product": "codex_cli",
                "status": "failed",
                "version": None,
                "location": codex_path,
                "source": codex_source,
                "sha256": None,
                "reason": "codex_cli_execution_failed",
                "message": f"codex --version failed: {detail or f'exit code {result.returncode}'}",
            }

        return {
            "product": "codex_cli",
            "status": "verified",
            "version": version_text or None,
            "location": codex_path,
            "source": codex_source,
            "sha256": None,
            "reason": None,
            "message": "Codex CLI detected and executable.",
        }

    def _product_observation(self, product: str, request: Mapping[str, Any]) -> dict[str, Any]:
        if product == "official_unity_cli":
            executable = self.which_fn("unity") or self.which_fn("unity-cli")
            return {
                "product": product,
                "status": "verified" if executable else "unavailable",
                "version": None,
                "location": executable,
                "source": "PATH",
                "sha256": None,
            }
        if product == "unity_artist_cli":
            executable = self.which_fn("unity-artist")
            package_id, package_version = _package_version(self.project_root)
            status = "verified" if executable and package_version else "unavailable"
            return {
                "product": product,
                "status": status,
                "version": package_version,
                "location": executable,
                "source": package_id or "project manifest",
                "sha256": None,
            }
        if product == "codex_cli":
            return self._observe_codex_cli(request)
        if product == "unity_agent_codex_plugin":
            codex_path, _, codex_reason = self._resolve_codex_cli(request.get("codex_cli_path"))
            result = observe_codex_plugin(codex_path, runner=self.command_runner)
            result["codex_cli_path"] = codex_path
            if codex_reason and not result.get("reason"):
                result["reason"] = codex_reason
            return result
        raise ValueError(f"unsupported setup product: {product}")

    def doctor(self, request: Mapping[str, Any]) -> dict[str, Any]:
        products = [str(item) for item in request["products"]]
        entries = [self._product_observation(product, request) for product in products]
        statuses = {str(entry["status"]) for entry in entries}
        status = "passed" if statuses == {"verified"} else ("failed" if "failed" in statuses else "unavailable")
        errors = [
            str(entry.get("message") or entry.get("reason") or "toolchain product unavailable")
            for entry in entries
            if str(entry.get("status")) not in {"verified", "installed"}
        ]
        return {
            "schema_version": "1.0",
            "operation": "doctor",
            "status": status,
            "project_root": str(self.project_root),
            "channel": CHANNEL,
            "entries": entries,
            "observed_at": _now(),
            "errors": errors,
        }

    @staticmethod
    def _action_for(entry: Mapping[str, Any]) -> str:
        status = str(entry.get("status") or "")
        product = str(entry.get("product") or "")
        if status == "verified":
            return "verify"
        if product == "codex_cli":
            return "manual_required"
        if product == "unity_agent_codex_plugin" and entry.get("reason") in {
            "codex_cli_unavailable",
            "codex_cli_override_missing",
        }:
            return "blocked_by_dependency"
        if product == "unity_agent_codex_plugin" and status == "failed":
            return "blocked_by_observation"
        return "install_then_verify"

    def plan(self, request: Mapping[str, Any]) -> dict[str, Any]:
        report = self.doctor(request)
        actions = [
            {
                "product": entry["product"],
                "action": self._action_for(entry),
                "target": "user_scope",
                "location": entry.get("location"),
                "version": entry.get("version"),
                "source": entry.get("source"),
                "reason": entry.get("reason"),
                "codex_cli_path": entry.get("codex_cli_path"),
            }
            for entry in report["entries"]
        ]
        plan_id = _plan_id(str(self.project_root), request["products"], report)
        blocked = any(action["action"] in {"manual_required", "blocked_by_dependency", "blocked_by_observation"} for action in actions)
        return {
            "schema_version": "1.0",
            "operation": "plan",
            "status": "unavailable" if blocked else "passed",
            "project_root": str(self.project_root),
            "channel": CHANNEL,
            "plan_id": plan_id,
            "doctor": report,
            "actions": actions,
            "install_root": request.get("install_root"),
            "approval_required": any(action["action"] == "install_then_verify" for action in actions),
            "observed_at": _now(),
        }

    def apply(
        self,
        request: Mapping[str, Any],
        *,
        approval_complete: bool = False,
        approved_plan: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not request.get("approval_ref") or approval_complete is not True:
            return {
                "schema_version": "1.0", "operation": "apply", "status": "failed",
                "failure_class": "blocked_by_approval", "reason": "approved plan and approval_ref are required",
                "project_root": str(self.project_root), "channel": CHANNEL,
            }
        if not approved_plan or str(approved_plan.get("plan_id") or "") != str(request.get("expected_plan_id") or ""):
            return {
                "schema_version": "1.0", "operation": "apply", "status": "failed",
                "failure_class": "stale_revision", "reason": "expected_plan_id does not match the approved plan",
                "project_root": str(self.project_root), "channel": CHANNEL,
            }
        approved_status = approved_plan.get("status")
        if approved_status is not None and str(approved_status) != "passed":
            return {
                "schema_version": "1.0", "operation": "apply", "status": "failed",
                "failure_class": "blocked_by_environment", "reason": "approved setup plan is not executable",
                "project_root": str(self.project_root), "channel": CHANNEL,
            }
        try:
            outcome = dict(self.installer_fn(approved_plan))
        except (OSError, ValueError, ReleaseInstallError) as exc:
            return {
                "schema_version": "1.0", "operation": "apply", "status": "failed",
                "failure_class": "execution_failed", "reason": str(exc),
                "project_root": str(self.project_root), "channel": CHANNEL,
            }
        outcome.setdefault("schema_version", "1.0")
        outcome.setdefault("operation", "apply")
        outcome.setdefault("project_root", str(self.project_root))
        outcome.setdefault("channel", CHANNEL)
        outcome.setdefault("observed_at", _now())
        return outcome

    def execute(
        self,
        request: Mapping[str, Any],
        *,
        approval_complete: bool = False,
        approved_plan: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_toolchain_setup_request(dict(request))
        if Path(request["project_root"]).expanduser().resolve(strict=False) != self.project_root:
            raise ValueError("Toolchain setup project_root does not match Installer Provider binding")
        operation = str(request["operation"])
        if operation == "doctor":
            return self.doctor(request)
        if operation == "plan":
            return self.plan(request)
        return self.apply(request, approval_complete=approval_complete, approved_plan=approved_plan)
