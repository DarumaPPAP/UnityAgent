"""Project a Grounding Bundle into Context-owned references."""

from __future__ import annotations

from typing import Any

from RAG.Contracts.models import GroundingBundle


def project_grounding_bundle(bundle: GroundingBundle) -> dict[str, Any]:
    """Return references only; Context decides selection, budget, and materialization."""

    source_refs: list[str] = []
    for item in bundle.items:
        provenance = item.get("provenance") or {}
        ref = str(provenance.get("source_ref") or "").strip()
        if ref and ref not in source_refs:
            source_refs.append(ref)
    return {
        "grounding_bundle_ref": bundle.reference,
        "source_refs": source_refs,
        "selected_count": len(bundle.items),
        "status": bundle.status,
        "bundle_revision": bundle.grounding_bundle_id,
    }
