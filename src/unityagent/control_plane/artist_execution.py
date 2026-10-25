"""既存EntryからArtistをContext、ToolBroker、永続Evidenceへ接続する。"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import uuid

from unityagent.context.manifest.build import build as build_context_manifest
from unityagent.context.manifest.validate import validate as validate_context_manifest
from unityagent.context.selection.project_context_inputs import derive_context_inputs
from unityagent.control_plane.artist_approval import approve_artist_plan, register_artist_plan, _plan_path
from unityagent.control_plane.artist_authority import ArtistAuthority
from unityagent.orchestration.routing.route_selector import resolve_specialist
from unityagent.persistence.evidence.runtime_adapter import append_runtime_execution_evidence
from unityagent.persistence.store.atomic_store import exclusive_file_lock, read_json, relative_ref, safe_id, sha256_json, write_immutable_json
from unityagent.policy.security.capability_policy import policy_for_capability
from unityagent.resources import resource_root
from unityagent.runtime.contracts.artist_plan import validate_artist_plan
from unityagent.runtime.contracts.capability_contract import validate_capability_request
from unityagent.runtime.evidence_capture.tool_runtime_evidence import normalize_provider_result
from unityagent.runtime.tooling.capability_resolver import ResolutionContext
from unityagent.runtime.tooling.environment.discovery import discover_environment
from unityagent.runtime.tooling.environment.project_identity import canonicalize_project_root, same_project_root
from unityagent.runtime.tooling.providers.unity_cli.artist_command_adapter import ArtistCommand
from unityagent.runtime.tooling.providers.unity_cli.result_mapper import parse_json_sequence
from unityagent.runtime.tooling.providers.unity_cli.unity_cli_provider import UnityCliProvider


def _session_path(plane, run_id):
    return plane.state_store.layout.root / "artist-runs" / safe_id(run_id, "run_id") / "context.json"


def _scope(scope):
    value = deepcopy(scope) if scope is not None else {"allowed_paths": ["Assets"], "prohibited_paths": ["Packages", "ProjectSettings"]}
    request = {"schema_version": "1.0", "capability": "domain.workflow", "operation_kind": "editor_mutation", "project_root": "scope-validation", "required_evidence": ["domain_result", "mutation_evidence"], "mutation_scope": value, "approval_ref": None, "preferred_surface": "editor"}
    validate_capability_request(request)
    return value


def _validate_session(session, project_root, run_id, scope, domain):
    if session.get("digest") != sha256_json({key: item for key, item in session.items() if key != "digest"}) or session.get("run_id") != run_id or not same_project_root(session.get("project_root", ""), project_root):
        raise ValueError("Artist run Context belongs to a different Project or Run")
    if scope is not None and _scope(scope) != session["scope"] or domain is not None and domain != session["domain"]:
        raise ValueError("Artist domain or reviewed scope changed; use a new Run")
    manifest = session["manifest"]
    view = manifest["materialized_context"]
    if manifest["run_id"] != run_id or view["run_id"] != run_id or (view.get("specialist_context") or {}).get("profile_id") != "artist_subagent":
        raise ValueError("Artist run does not carry its materialized Specialist Context")
    # 保存したContextの選択元が変わった場合は、古い承認へ新しい文脈を混ぜない。
    for item in view["context_fingerprint"]["selected_source_revisions"]:
        if item["ref"].startswith("specialist:"):
            continue
        path = resource_root() / item["ref"]
        if "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != item["revision"]:
            raise ValueError("Artist Context source changed; use a new Run")
    return session


def _context(plane, project_root, run_id, command, snapshot, *, scope=None, domain=None):
    path = _session_path(plane, run_id)
    requested_domain = "cinematic" if command.name == "cinematic" else domain
    if requested_domain is not None and requested_domain not in {"visual_art", "cinematic"}:
        raise ValueError("Artist domain is invalid")
    with exclusive_file_lock(path.with_suffix(".lock")):
        if path.exists():
            session = _validate_session(read_json(path), project_root, run_id, scope, requested_domain)
            if command.name == "cinematic":
                requested = parse_json_sequence(command.request_json, strict=True)[0] if command.request_json else {}
                director = requested.get("directorName")
                bound = session.get("cinematic_director")
                if director and director != bound or (command.operation or "inspect") != "inspect" and not bound:
                    raise ValueError("Cinematic Director differs from materialized Context; use a new Run")
            return session
        actual_domain = requested_domain or "visual_art"
        route = "artist-cinematic" if actual_domain == "cinematic" else "artist-lookdev"
        reviewed_scope = _scope(scope)
        intent_value = parse_json_sequence(command.request_json, strict=True)[0] if command.request_json else {"operation": command.operation or command.name, "inspection_domain": actual_domain}
        intent = {"kind": "visual_capture", "visual_intent": json.dumps(intent_value, ensure_ascii=False, sort_keys=True), "exact_scene_or_asset_scope": json.dumps(reviewed_scope, sort_keys=True), "reference_or_visual_definition": "Explicit typed Artist request, Editor exact Plan and human Capture Review; no automatic acceptance"}
        inputs = derive_context_inputs(project_root, snapshot, intent)
        if actual_domain == "cinematic":
            inspecting = command.name != "cinematic" or (command.operation or "inspect") == "inspect"
            if not inspecting and not intent_value.get("directorName"):
                raise ValueError("Cinematic planning Context requires an exact directorName")
            provenance = {"source_kind": "orchestration_projection", "revision": inputs["bindings"]["visual_intent"]["revision"], "freshness": deepcopy(inputs["bindings"]["visual_intent"]["freshness"])}
            inputs["bindings"].update({"cinematic_intent": inputs["bindings"]["visual_intent"], "exact_playable_director_or_timeline_scope": {**provenance, "value": json.dumps({"directorName": intent_value.get("directorName", "unknown"), "inspection_domain": actual_domain, "read_only": inspecting}, sort_keys=True)}, "shot_and_binding_definition": {**provenance, "value": json.dumps(intent_value, sort_keys=True)}})
        specialist_capability = "artist.camera.inspect" if command.name in {"inspect", "history"} else "visual.capture" if command.name in {"capture", "evaluate"} else "artist.camera.refine"
        selection = resolve_specialist(route, specialist_capability, snapshot)
        if selection.get("status") != "selected" or selection.get("profile_id") != "artist_subagent":
            raise ValueError("Artist Specialist eligibility was not observed")
        manifest = build_context_manifest(run_id, route, project_facts=inputs["project_facts"], bindings=inputs["bindings"], capability_ids=["scene.inspect", "visual.capture", "domain.workflow"], specialist_selection=selection, specialist_items=inputs["specialist_items"], specialist_tags=inputs["specialist_tags"], required_specialist_keys=inputs["required_specialist_keys"])
        if manifest["budget_report"]["decision"] != "within_budget" or manifest["unresolved_bindings"]:
            raise ValueError("Artist Context budget or required bindings are incomplete")
        manifest_path = plane.state_store.layout.snapshot(run_id, "context-manifest", sha256_json(manifest))
        write_immutable_json(manifest_path, manifest)
        validate_context_manifest(manifest_path)
        session = {"schema_version": "1.0", "project_root": project_root, "run_id": run_id, "domain": actual_domain, "scope": reviewed_scope, "manifest": manifest, "manifest_ref": relative_ref(plane.state_store.layout.root, manifest_path)}
        if actual_domain == "cinematic":
            session["cinematic_director"] = intent_value.get("directorName")
        session["digest"] = sha256_json(session)
        write_immutable_json(path, session)
        return session


def _artifact_path(plane, run_id, kind, identifier):
    return _session_path(plane, run_id).parent / kind / (safe_id(identifier) + ".json")


def approve_artist_execution(plane, project_root, run_id, plan_id, *, expires_at=None):
    project = canonicalize_project_root(project_root)
    session = _validate_session(read_json(_session_path(plane, run_id)), project, run_id, None, None)
    plan = validate_artist_plan(read_json(_plan_path(plane.state_store.layout.root, plan_id)))
    view = session["manifest"]["materialized_context"]
    if not same_project_root(plan["project_root"], project) or plan["run_id"] != run_id or plan["context_id"] != view["context_id"] or plan["context_fingerprint"] != view["context_fingerprint"]["value"]:
        raise ValueError("Artist approval does not match this Run's Project and materialized Context")
    return approve_artist_plan(plane, plan_id, expires_at=expires_at)


def execute_artist(plane, project_root, run_id, command, *, definition_fingerprint, scope=None, approval_ref=None, timeout_seconds=120.0, cancel_event=None, domain=None):
    if not isinstance(command, ArtistCommand) or command.context_json is not None or command.approval_token is not None:
        raise ValueError("Artist Entry cannot accept caller-authored Context or authorization tokens")
    project = canonicalize_project_root(project_root)
    run_id = safe_id(run_id, "run_id")
    if cancel_event is not None and cancel_event.is_set():
        raise ValueError("Artist execution was cancelled before dispatch")
    observed = discover_environment(project)
    snapshot = observed.to_dict() if hasattr(observed, "to_dict") else observed
    session = _context(plane, project, run_id, command, snapshot, scope=scope, domain=domain)
    view = session["manifest"]["materialized_context"]
    context_id, fingerprint = view["context_id"], view["context_fingerprint"]["value"]
    transport = json.dumps({"contextId": context_id, "contextFingerprint": fingerprint, "projectRoot": project, "runId": run_id}, separators=(",", ":"), ensure_ascii=False)
    command = replace(command, context_json=transport)
    if command.name == "evaluate":
        command = replace(command, decision=command.decision.strip().lower() if isinstance(command.decision, str) else None)
        capture = read_json(_artifact_path(plane, run_id, "captures", command.capture_id))
        plane.evidence_store.verify_record(capture["evidence_id"], expected_run_id=run_id)
        if capture["context_id"] != context_id or capture["context_fingerprint"] != fingerprint or not same_project_root(capture["project_root"], project):
            raise ValueError("Capture belongs to another materialized Context or Project")
        review = {"captureId": command.capture_id, "decision": command.decision, "notes": command.notes or ""}
        review_plan = register_artist_plan(plane, project, run_id, "artist.evaluate", capture["payload"], context_id, fingerprint, session["scope"], review=review)
        if not approval_ref:
            # Review計画の保存だけではHuman DecisionやEditor成功Evidenceを発行しない。
            return {"status": "planned", "run_id": run_id, "approval_plan_id": review_plan["plan_id"], "context_id": context_id, "context_fingerprint": fingerprint, "human_review": "not_observed", "evidence_refs": []}
    mutation = command.name == "apply" or command.name == "cinematic" and command.operation == "apply"
    authenticated = mutation or command.name == "evaluate"
    authority = None
    if authenticated:
        if not approval_ref:
            raise ValueError("Artist execution requires explicit Plan approval")
        identifier = command.capture_id if command.name == "evaluate" else command.plan_id
        decision = plane.approval_resolver.resolve_artist_plan(approval_ref, project_root=project, run_id=run_id, plan_id=identifier)
        binding = decision["binding"]
        if binding["command"] != "artist." + command.name or binding["receivedContextId"] != context_id or binding["receivedContextFingerprint"] != fingerprint or {key: binding["scope"].get(key) for key in ("allowed_paths", "prohibited_paths")} != session["scope"]:
            raise ValueError("Artist approved command, Scope or Context differs")
        if command.expected_revision is not None and command.expected_revision != binding["expectedRevision"]:
            raise ValueError("Artist expected Revision differs from the approved Plan")
        if plane.approval_resolver.store.get(approval_ref).get("artist_consumption") is not None:
            raise ValueError("Artist approval has already started execution")
        authority = ArtistAuthority.for_plan(resolver=plane.approval_resolver, store=plane.approval_resolver.store, binding=binding, decision=decision)
        command = replace(command, approval_token=authority.token, expected_revision=binding["expectedRevision"] if mutation else command.expected_revision)
    capability = "domain.workflow" if mutation else "visual.capture" if command.name == "capture" else "scene.inspect"
    required = ["domain_result", "mutation_evidence"] if mutation else ["visual_capture"] if capability == "visual.capture" else ["editor_observation"]
    request = {"schema_version": "1.0", "capability": capability, "project_root": project, "operation_kind": "editor_mutation" if mutation else "read", "required_evidence": required, "mutation_scope": session["scope"] if mutation else None, "approval_ref": approval_ref, "preferred_surface": "editor", "qualifiers": {"domain": session["domain"], "workflow": "cinematic_" + (command.operation or "inspect") if command.name == "cinematic" else command.name}}
    validate_capability_request(request)
    provider = UnityCliProvider(project, snapshot)
    arguments = {"artist_command": command, "artist_authority": authority, "timeout_seconds": timeout_seconds, "cancel_event": cancel_event}
    execution_context = {"schema_version": "1.0", "context_id": context_id, "context_fingerprint": fingerprint, "run_id": run_id, "specialist_context": deepcopy(view["specialist_context"])}
    policy = policy_for_capability(capability)
    expected_permission = "explicit_mutation_permission" if mutation else "read_only"
    expected_approval = "required_for_project_asset_or_settings_change" if mutation else "not_required"
    if policy.get("operation_kind") != request["operation_kind"] or policy.get("default_permission") != expected_permission or policy.get("approval_requirement") != expected_approval or policy.get("requires_mutation_scope") is not mutation:
        raise ValueError("Policy does not allow this typed Artist execution")
    if not set(policy["minimum_required_evidence"]).issubset(required):
        raise ValueError("Policy requires additional Artist Evidence")
    context = ResolutionContext(policy_allowed=True, approval_required=authenticated, approval_complete=authenticated)
    with authority if authority is not None else nullcontext():
        result = plane.broker.dispatch(request, snapshot, context=context, executors={"unity_cli": provider.execute}, provider_arguments={"unity_cli": arguments}, specialist_execution_context=execution_context, specialist_context_manifest_path=str(plane.state_store.layout.root / session["manifest_ref"]), receipt_required=True, maximum_retry_attempts=0)
    refs = []
    provider_result = result.get("provider_result")
    if (result.get("resolution") or {}).get("status") == "resolved" and isinstance(provider_result, dict):
        raw_path = plane.state_store.layout.snapshot(run_id, "provider-result", sha256_json(provider_result))
        write_immutable_json(raw_path, provider_result)
        raw_ref = relative_ref(plane.state_store.layout.root, raw_path)
        step_id = "artist-" + command.name + "-" + uuid.uuid4().hex[:12]
        evidence = normalize_provider_result(request, result["resolution"], snapshot, provider_result, run_id=run_id, step_id=step_id, evidence_id=step_id + "-evidence", definition_fingerprint=definition_fingerprint, structured_result_ref=raw_ref, raw_refs=[raw_ref], registry=plane.broker.registry)
        persisted = append_runtime_execution_evidence(plane.evidence_store, evidence)
        refs.append(persisted["evidence_id"])
    response = {**result, "run_id": run_id, "context_id": context_id, "context_fingerprint": fingerprint, "evidence_refs": refs, "durable": bool(refs), "save_state": "not_saved"}
    if result.get("status") == "completed" and result.get("receipt_integrity") == "verified" and refs and provider_result.get("status") == "passed":
        payload = provider_result.get("payload") or {}
        planned = command.name in {"plan", "preview", "refine"} or command.name == "cinematic" and command.operation in {"plan", "preview"}
        if planned:
            plan = register_artist_plan(plane, project, run_id, "artist.cinematic" if command.name == "cinematic" else "artist.apply", payload, context_id, fingerprint, session["scope"])
            response["approval_plan_id"] = plan["plan_id"]
        if command.name == "capture":
            capture = {"payload": payload, "evidence_id": refs[0], "project_root": project, "context_id": context_id, "context_fingerprint": fingerprint}
            write_immutable_json(_artifact_path(plane, run_id, "captures", payload["captureId"]), capture)
    plane._save_execution_state(run_id=run_id, step_id="artist-" + command.name, action_id=capability, status=result["status"], evidence_refs=refs)
    return response
