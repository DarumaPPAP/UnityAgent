import tempfile
import unittest
from pathlib import Path

import jsonschema
import yaml

from Operations.ChangeManagement.change_manager import (
    ChangeManagementError,
    apply_authorized_change,
    authorize_change,
    build_change_request,
    build_version_manifest,
)
from Operations.ChangeManagement.operations_api import ChangeManagementOperationsAPI
from Operations.Detection.detector import detect_async_failures
from Operations.Incidents.incident_manager import build_incident, transition_incident
from Operations.Observability.event_store import OperationalEventStore
from Operations.RuntimeControl.control_gateway import (
    OperationalControlError,
    authorize_control,
    dispatch_approved_control,
    validate_approved_command,
)
from Orchestration.Control.operations_api import OrchestrationOperationsAPI
from Runtime.Control.operations_api import RuntimeOperationsAPI
from Runtime.Telemetry.runtime_telemetry import runtime_audit, runtime_log, runtime_metric, runtime_span


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(relative: str) -> dict:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8")) or {}


def fingerprint() -> dict:
    return {
        "schema_version": "1.0",
        "architecture_version": "3.1",
        "policy_revision": "policy-7",
        "prompt_revision": "prompt-7",
        "context_revision": "context-7",
        "graph_revision": "graph-7",
        "runtime_profile_revision": "runtime-7",
        "tool_schema_revision": "tools-7",
        "checkpoint_schema_revision": "1.1",
        "evidence_schema_revision": "1.1",
        "eval_contract_revision": "eval-7",
    }


def control_request(action: str, **overrides) -> dict:
    value = {
        "schema_version": "1.0",
        "request_id": f"request-{action}",
        "action": action,
        "run_id": "run-7",
        "route_id": None,
        "requested_by": "operator:test",
        "reason": "phase7 test",
        "parameters": {},
        "requested_at": "2026-08-29T06:00:00Z",
    }
    value.update(overrides)
    return value


def policy_decision(action: str, *, risk: str = "R2", approval_required: bool = True, allowed: bool = True) -> dict:
    return {
        "allowed": allowed,
        "action": action,
        "risk_level": risk,
        "approval_required": approval_required,
        "policy_revision": "policy-7",
    }


def approval(*, required: bool = True) -> dict:
    return {"status": "approved", "approval_id": "approval-7"} if required else {"status": "not_required", "approval_id": None}


class Phase7OperationsTests(unittest.TestCase):
    def test_runtime_emits_all_observability_contracts(self):
        trace = runtime_span(
            run_id="run-7", step_id="step-7", event="tool.completed", span_id="span-7",
            timestamp="2026-08-29T06:00:00Z", evidence_refs=["ev-7"],
        )
        metric = runtime_metric(
            run_id="run-7", step_id="step-7", metric_name="runtime.latency_ms", value=12, unit="ms",
            event_id="metric-7", timestamp="2026-08-29T06:00:00Z",
        )
        log = runtime_log(
            run_id="run-7", step_id="step-7", logger="runtime", message="done", event_id="log-7",
            timestamp="2026-08-29T06:00:00Z",
        )
        audit = runtime_audit(
            run_id="run-7", action="tool.execute", target="tool:test", outcome="applied",
            policy_revision="policy-7", approval_id=None, event_id="audit-7", timestamp="2026-08-29T06:00:00Z",
        )
        cases = [
            ("Operations/Observability/trace-record.schema.yaml", trace),
            ("Operations/Observability/metric-event.schema.yaml", metric),
            ("Operations/Observability/structured-log-event.schema.yaml", log),
            ("Operations/Observability/audit-event.schema.yaml", audit),
        ]
        for schema_path, value in cases:
            jsonschema.Draft202012Validator(load_yaml(schema_path), format_checker=jsonschema.FormatChecker()).validate(value)

    def test_operational_backend_append_query_and_search_are_separate_from_evidence_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            store = OperationalEventStore(Path(temp))
            trace = runtime_span(
                run_id="run-7", step_id=None, event="runtime.retry", span_id="span-a",
                timestamp="2026-08-29T06:00:00Z", evidence_refs=["evidence:durable-1"],
            )
            store.append("trace", trace)
            rows = store.query(record_type="trace", run_id="run-7")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["evidence_refs"], ["evidence:durable-1"])
            self.assertEqual(rows[0]["_operations_record_type"], "trace")
            self.assertEqual(len(store.search_text("runtime.retry")), 1)

    def test_async_detection_retry_latency_route_and_correlation(self):
        traces = [
            runtime_span(run_id="run-7", step_id=None, event="runtime.retry", span_id=f"retry-{index}", timestamp="2026-08-29T06:00:00Z")
            for index in range(3)
        ]
        traces.append(runtime_span(
            run_id="run-7", step_id=None, event="route.observed", span_id="route-1",
            attributes={"expected_route": "csharp-local-fix", "actual_route": "architecture-design"},
            timestamp="2026-08-29T06:00:00Z",
        ))
        metrics = [runtime_metric(
            run_id="run-7", step_id=None, metric_name="runtime.latency_ms", value=9000, unit="ms",
            event_id="metric-latency", timestamp="2026-08-29T06:00:00Z",
        )]
        detections = detect_async_failures(trace_events=traces, metric_events=metrics, observed_at="2026-08-29T06:01:00Z")
        kinds = {item["kind"] for item in detections}
        self.assertTrue({"retry_storm", "latency_drift", "route_drift", "correlated_incident"}.issubset(kinds))
        for detection in detections:
            jsonschema.Draft202012Validator(load_yaml("Operations/Detection/detection-event.schema.yaml"), format_checker=jsonschema.FormatChecker()).validate(detection)

    def test_quality_drift_ignores_not_observed_eval_records(self):
        evals = [
            {"eval_id": "eval-pass", "run_id": "run-a", "failure_class": None, "quality_denominator_eligible": True},
            {"eval_id": "eval-fail-1", "run_id": "run-b", "failure_class": "agent_behavior_regression", "quality_denominator_eligible": True},
            {"eval_id": "eval-fail-2", "run_id": "run-c", "failure_class": "agent_behavior_regression", "quality_denominator_eligible": True},
            {"eval_id": "eval-timeout", "run_id": "run-d", "failure_class": "runtime_timeout", "quality_denominator_eligible": False},
        ]
        detections = detect_async_failures(eval_records=evals, observed_at="2026-08-29T06:01:00Z")
        quality = [item for item in detections if item["kind"] == "quality_drift"]
        self.assertEqual(len(quality), 1)
        self.assertEqual(quality[0]["attributes"]["sample_count"], 3)

    def test_incident_contract_and_transitions(self):
        detections = detect_async_failures(
            trace_events=[
                runtime_span(run_id="run-7", step_id=None, event="runtime.retry", span_id=f"r{index}", timestamp="2026-08-29T06:00:00Z")
                for index in range(3)
            ],
            metric_events=[runtime_metric(
                run_id="run-7", step_id=None, metric_name="runtime.cost_usd", value=5, unit="usd",
                event_id="cost", timestamp="2026-08-29T06:00:00Z",
            )],
            observed_at="2026-08-29T06:01:00Z",
        )
        incident = build_incident(detections, created_at="2026-08-29T06:02:00Z")
        jsonschema.Draft202012Validator(load_yaml("Operations/Incidents/incident.schema.yaml"), format_checker=jsonschema.FormatChecker()).validate(incident)
        mitigated = transition_incident(incident, "mitigated", updated_at="2026-08-29T06:03:00Z")
        resolved = transition_incident(mitigated, "resolved", updated_at="2026-08-29T06:04:00Z")
        self.assertEqual(resolved["status"], "resolved")
        with self.assertRaises(ValueError):
            transition_incident(resolved, "open")

    def test_runbook_catalog_matches_runbook_contract(self):
        schema = load_yaml("Operations/Incidents/runbook.schema.yaml")
        catalog = load_yaml("Operations/Incidents/runbooks.yaml")
        for runbook_id, value in catalog["runbooks"].items():
            document = {"schema_version": "1.0", "runbook_id": runbook_id, **value}
            jsonschema.Draft202012Validator(schema).validate(document)
            for step in document["steps"]:
                if step["kind"] == "control":
                    self.assertTrue(step["requires_human_gate"])

    def test_policy_and_approval_gate_before_runtime_dispatch(self):
        request = control_request("pause")
        command = authorize_control(
            request,
            policy_decision=policy_decision("pause", risk="R2", approval_required=True),
            approval_decision=approval(required=True),
            authorized_at="2026-08-29T06:05:00Z",
        )
        jsonschema.Draft202012Validator(load_yaml("Operations/RuntimeControl/approved-control-command.schema.yaml"), format_checker=jsonschema.FormatChecker()).validate(command)
        calls = []
        runtime_api = RuntimeOperationsAPI({"pause": lambda value: calls.append(value["command_id"]) or "paused"})
        result = dispatch_approved_control(command, ports={"Runtime": runtime_api.handle})
        self.assertEqual(result, "paused")
        self.assertEqual(calls, [command["command_id"]])

    def test_policy_denial_and_missing_approval_fail_closed(self):
        request = control_request("pause")
        with self.assertRaises(OperationalControlError):
            authorize_control(
                request,
                policy_decision=policy_decision("pause", allowed=False),
                approval_decision=approval(required=True),
            )
        with self.assertRaises(OperationalControlError):
            authorize_control(
                request,
                policy_decision=policy_decision("pause", approval_required=True),
                approval_decision={"status": "not_required", "approval_id": None},
            )

    def test_authorization_hash_blocks_tampering_and_raw_runtime_request(self):
        command = authorize_control(
            control_request("pause"),
            policy_decision=policy_decision("pause"),
            approval_decision=approval(),
        )
        tampered = dict(command)
        tampered["action"] = "stop"
        with self.assertRaises(OperationalControlError):
            validate_approved_command(tampered)
        runtime_api = RuntimeOperationsAPI({"pause": lambda value: value})
        with self.assertRaises(ValueError):
            runtime_api.handle(control_request("pause"))

    def test_orchestration_controls_use_approved_api(self):
        request = control_request("disable_route", run_id=None, route_id="rendering-incident")
        command = authorize_control(
            request,
            policy_decision=policy_decision("disable_route", risk="R3", approval_required=True),
            approval_decision=approval(),
        )
        orchestration_api = OrchestrationOperationsAPI({"disable_route": lambda value: value["route_id"]})
        self.assertEqual(
            dispatch_approved_control(command, ports={"Orchestration": orchestration_api.handle}),
            "rendering-incident",
        )

    def test_checkpoint_replay_requires_resume_decision_reference(self):
        bad = control_request("replay_checkpoint", parameters={"checkpoint_id": "checkpoint-7"})
        with self.assertRaises(OperationalControlError):
            authorize_control(
                bad,
                policy_decision=policy_decision("replay_checkpoint", risk="R3"),
                approval_decision=approval(),
            )
        good = control_request(
            "replay_checkpoint",
            parameters={"checkpoint_id": "checkpoint-7", "resume_decision_ref": "resume:decision-7"},
        )
        command = authorize_control(
            good,
            policy_decision=policy_decision("replay_checkpoint", risk="R3"),
            approval_decision=approval(),
        )
        orchestration_api = OrchestrationOperationsAPI({"replay_checkpoint": lambda value: value["parameters"]["checkpoint_id"]})
        self.assertEqual(dispatch_approved_control(command, ports={"Orchestration": orchestration_api.handle}), "checkpoint-7")

    def test_r4_rollback_cannot_bypass_approval(self):
        request = control_request("rollback_config", run_id=None, parameters={"target_manifest_id": "manifest-old"})
        with self.assertRaises(OperationalControlError):
            authorize_control(
                request,
                policy_decision=policy_decision("rollback_config", risk="R4", approval_required=False),
                approval_decision=approval(required=False),
            )
        command = authorize_control(
            request,
            policy_decision=policy_decision("rollback_config", risk="R4", approval_required=True),
            approval_decision=approval(),
        )
        api = ChangeManagementOperationsAPI(lambda value: value["parameters"]["target_manifest_id"])
        self.assertEqual(dispatch_approved_control(command, ports={"ChangeManagement": api.handle}), "manifest-old")

    def test_version_manifest_and_change_management_are_approval_gated(self):
        manifest = build_version_manifest(
            fingerprint(), manifest_id="manifest-7", operations_revision="operations-7", generated_at="2026-08-29T06:00:00Z"
        )
        jsonschema.Draft202012Validator(load_yaml("Operations/ChangeManagement/version-manifest.schema.yaml"), format_checker=jsonschema.FormatChecker()).validate(manifest)
        change = build_change_request(
            change_id="change-7", kind="rollout", current_manifest_id="manifest-6", target_manifest_id="manifest-7",
            summary="Phase 7 rollout", source_change_proposal_refs=["proposal-7"], created_at="2026-08-29T06:00:00Z",
        )
        with self.assertRaises(ChangeManagementError):
            apply_authorized_change(change, apply_port=lambda value: value)
        authorized = authorize_change(
            change,
            policy_decision={"allowed": True, "approval_required": True, "decision_ref": "policy-decision-7"},
            approval_decision={"status": "approved", "decision_ref": "approval-decision-7"},
        )
        applied, result = apply_authorized_change(authorized, apply_port=lambda value: value["target_manifest_id"])
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(result, "manifest-7")

    def test_operations_does_not_reach_runtime_execution_control_internals(self):
        forbidden = ("Runtime.ExecutionControl", "Runtime/ExecutionControl", "process_runtime", "subprocess")
        for path in (ROOT / "Operations").rglob("*.py"):
            if "Tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, f"{path}: {token}")

    def test_action_catalog_is_complete_and_separates_authorities(self):
        catalog = load_yaml("Operations/RuntimeControl/action-catalog.yaml")
        self.assertEqual(
            set(catalog["actions"]),
            {"pause", "resume", "stop", "quarantine", "disable_route", "rollback_config", "force_hitl", "switch_model", "replay_checkpoint"},
        )
        self.assertEqual(catalog["actions"]["stop"]["target_authority"], "Runtime")
        self.assertEqual(catalog["actions"]["disable_route"]["target_authority"], "Orchestration")
        self.assertEqual(catalog["actions"]["rollback_config"]["target_authority"], "ChangeManagement")


if __name__ == "__main__":
    unittest.main()
