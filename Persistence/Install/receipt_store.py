"""Append-immutable InstallReceipt store owned by Persistence."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from Persistence.Store.atomic_store import (
    PersistenceError,
    append_jsonl,
    read_json,
    sha256_json,
    write_immutable_json,
)
from Persistence.Store.layout import PersistenceLayout


class InstallReceiptStore:
    """Persist verified toolchain installation facts without importing Runtime."""

    def __init__(self, root) -> None:
        self.layout = PersistenceLayout(root)

    @staticmethod
    def _validate(receipt: dict[str, Any]) -> None:
        required = {"schema_version", "receipt_id", "run_id", "project_root", "channel", "entries", "verified_at", "evidence_refs"}
        missing = sorted(required - set(receipt))
        if missing:
            raise PersistenceError("contract_missing_field", f"InstallReceipt missing required fields: {missing}")
        if receipt.get("schema_version") != "1.0" or receipt.get("channel") != "0.0.3-beta":
            raise PersistenceError("invalid_install_receipt", "unsupported InstallReceipt schema or channel")
        if not isinstance(receipt.get("entries"), list) or not receipt["entries"]:
            raise PersistenceError("invalid_install_receipt", "InstallReceipt entries must be non-empty")
        if not isinstance(receipt.get("evidence_refs"), list):
            raise PersistenceError("invalid_install_receipt", "InstallReceipt evidence_refs must be a list")
        for entry in receipt["entries"]:
            if not isinstance(entry, dict):
                raise PersistenceError("invalid_install_receipt", "InstallReceipt entry must be an object")
            if set(entry) != {"product", "status", "version", "location", "source", "sha256"}:
                raise PersistenceError("invalid_install_receipt", "InstallReceipt entry fields drifted")

    def append(self, receipt: dict[str, Any]) -> str:
        self._validate(receipt)
        path = self.layout.install_receipt(str(receipt["receipt_id"]))
        created = write_immutable_json(path, deepcopy(receipt))
        if created:
            append_jsonl(
                self.layout.install_receipt_events(),
                {
                    "event": "install_receipt_appended",
                    "receipt_id": receipt["receipt_id"],
                    "run_id": receipt["run_id"],
                    "record_hash": sha256_json(receipt),
                },
            )
        return str(path.relative_to(self.layout.root).as_posix())

    def get(self, receipt_id: str) -> dict[str, Any]:
        return read_json(self.layout.install_receipt(receipt_id))
