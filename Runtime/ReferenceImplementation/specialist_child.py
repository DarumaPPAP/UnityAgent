"""Bounded UnityArtist specialist entrypoint.

The module intentionally exposes only the authenticated Runtime IPC client. It
does not import a shell, subprocess API, Unity executable, installer, or project
filesystem writer.
"""
from __future__ import annotations

import multiprocessing.connection as mp_connection
import os
from typing import Any

from .contracts import ApprovalDecision, SurfaceGrant, TaskContract, TypedAction
from .isolation import RuntimeIPCProtocol, SpecialistSession


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing authenticated specialist environment field: {name}")
    return value


def main() -> int:
    session = SpecialistSession(
        session_id=_required("UNITY_AGENT_SESSION_ID"),
        subagent_instance_id=_required("UNITY_AGENT_SUBAGENT_INSTANCE_ID"),
        nonce=_required("UNITY_AGENT_IPC_NONCE"),
        pipe_name=_required("UNITY_AGENT_IPC_ADDRESS"),
        task_id="pending",
        run_id="pending",
        grant_id=_required("UNITY_AGENT_GRANT_ID"),
        grant_digest=_required("UNITY_AGENT_GRANT_DIGEST"),
        created_at="",
        expires_at="",
    )
    connection = mp_connection.Client(session.pipe_name, family="AF_PIPE", authkey=bytes.fromhex(session.nonce))
    protocol = RuntimeIPCProtocol(session)
    connection.send(protocol.make("hello", {"subagent_instance_id": session.subagent_instance_id, "audience": "unity_artist"}))
    grant_message = protocol.accept(connection.recv())
    task = TaskContract.from_envelope(grant_message["payload"]["task_envelope"])
    grant = SurfaceGrant.from_envelope(grant_message["payload"]["grant_envelope"])
    context: dict[str, Any] = dict(grant_message["payload"].get("context") or {})
    expected_revision = str(context.get("expected_revision") or "")
    proposed_value = float(context.get("proposed_value", 43.0))
    connection.send(protocol.make("inspect", {"target_guid": task.scope["target_guids"][0], "property_path": "Camera.fieldOfView"}))
    action = TypedAction.propose(
        action_id=f"action-{task.run_id}",
        idempotency_key=f"{task.project_fingerprint}:{task.scope['target_guids'][0]}:Camera.fieldOfView",
        task=task,
        approval=ApprovalDecision.from_envelope(grant_message["payload"].get("approval_envelope")) if grant_message["payload"].get("approval_envelope") else ApprovalDecision.from_dict(context["approval"]),
        grant=grant,
        value=proposed_value,
        expected_revision=expected_revision,
    )
    # Runtime IPC carries typed contracts only through the versioned envelope.
    # Keeping the raw contract out of the wire prevents a receiver from
    # accidentally interpreting an untyped payload as an authority decision.
    connection.send(protocol.make("propose_action", {"action_envelope": action.to_envelope()}))
    connection.send(protocol.make("capture", {"capture": "camera_fov_observation", "observation_state": "observed"}))
    connection.send(protocol.make("evaluate", {"accepted": True, "reason": "bounded_camera_fov_refinement"}))
    connection.send(protocol.make("complete", {"evaluation": "accepted", "action_id": action.action_id}))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
