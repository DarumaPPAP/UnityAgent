"""Bounded Installer Provider for the UnityAgent Control Plane.

The adapter owns toolchain observation and approved installation mechanics. It is
never called by Entry directly; ToolBroker management dispatch is the only route.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Mapping, Sequence

from Runtime.Contracts.toolchain_setup_contract import validate_toolchain_setup_request
from Runtime.Tooling.Providers.Installer.release_installer import ReleaseInstallError, install_plan

PRODUCTS = frozenset({"official_unity_cli", "unity_artist_cli"})
PACKAGE_IDS = ("com.unity-artist", "com.darumappap.unity-artist")
CHANNEL = "0.0.1-beta"


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


class InstallerProvider:
    """Management Provider selected through the existing Runtime registry."""

    provider_id = "installer"
    operations = frozenset({"doctor", "plan", "apply"})

    def __init__(
        self,
        project_root: str | Path,
        *,
        which_fn: Callable[[str], str | None] = shutil.which,
        installer_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve(strict=False)
        self.which_fn = which_fn
        self.installer_fn = installer_fn or install_plan

    def _product_observation(self, product: str) -> dict[str, Any]:
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
        raise ValueError(f"unsupported setup product: {product}")

    def doctor(self, request: Mapping[str, Any]) -> dict[str, Any]:
        products = [str(item) for item in request["products"]]
        entries = [self._product_observation(product) for product in products]
        statuses = {str(entry["status"]) for entry in entries}
        status = "passed" if statuses == {"verified"} else ("failed" if "failed" in statuses else "unavailable")
        return {
            "schema_version": "1.0",
            "operation": "doctor",
            "status": status,
            "project_root": str(self.project_root),
            "channel": CHANNEL,
            "entries": entries,
            "observed_at": _now(),
            "errors": [] if status == "passed" else ["one or more requested toolchain products are unavailable"],
        }

    def plan(self, request: Mapping[str, Any]) -> dict[str, Any]:
        report = self.doctor(request)
        actions = [
            {
                "product": entry["product"],
                "action": "verify" if entry["status"] == "verified" else "install_then_verify",
                "target": "user_scope",
                "location": entry.get("location"),
                "version": entry.get("version"),
            }
            for entry in report["entries"]
        ]
        plan_id = _plan_id(str(self.project_root), request["products"], report)
        return {
            "schema_version": "1.0",
            "operation": "plan",
            "status": "passed",
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
        if self.installer_fn is None:
            return {
                "schema_version": "1.0", "operation": "apply", "status": "failed",
                "failure_class": "backend_not_implemented", "reason": "no approved installation adapter is registered",
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
