"""公式Unity CLIと任意Artist UPMの観測済みSetup計画を確認する。"""
from __future__ import annotations

from typing import Mapping

CONTROL_PLANE_CHANNEL = "0.0.8-beta"


class ReleaseInstallError(RuntimeError):
    pass


def install_plan(plan: Mapping[str, object]) -> dict[str, object]:
    """承認済み計画を処理する。配布物の取得や任意UPMの自動導入は行わない。"""
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ReleaseInstallError("approved setup plan has no actions")
    entries = []
    for action in actions:
        if not isinstance(action, Mapping):
            raise ReleaseInstallError("approved setup plan contains a malformed action")
        product = str(action.get("product") or "")
        if product not in {"official_unity_cli", "artist_subagent"}:
            raise ReleaseInstallError(f"unsupported install product: {product}")
        action_name = str(action.get("action") or "")
        if product == "artist_subagent" and action_name not in {"verify", "manual_required"}:
            raise ReleaseInstallError("ArtistSubAgent package requires explicit UPM setup")
        if product == "official_unity_cli" and action_name not in {"verify", "manual_required", "install_then_verify"}:
            raise ReleaseInstallError(f"unsupported installer action: {action_name}")
        verified = action_name == "verify"
        if verified and not action.get("location"):
            raise ReleaseInstallError("verify action requires an observed location")
        entries.append({"product": product, "status": "verified" if verified else "unavailable", "version": action.get("version") if verified else None, "location": action.get("location") if verified else None, "source": action.get("source") or ("project manifest" if product == "artist_subagent" else "Unity Hub / official Unity installation"), "sha256": None})
    status = "passed" if all(entry["status"] == "verified" for entry in entries) else "unavailable"
    channel = str(plan.get("channel") or CONTROL_PLANE_CHANNEL)
    return {"schema_version": "1.0", "operation": "apply", "status": status, "project_root": str(plan.get("project_root") or ""), "channel": channel, "plan_id": plan.get("plan_id"), "entries": entries, "install_receipt": {"schema_version": "1.0", "receipt_id": f"receipt-{plan.get('plan_id') or 'unknown'}", "run_id": "pending", "project_root": str(plan.get("project_root") or ""), "channel": channel, "entries": entries, "verified_at": "1970-01-01T00:00:00+00:00", "evidence_refs": []}}
