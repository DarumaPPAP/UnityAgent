from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path
import tempfile

from Persistence.Evidence.evidence_store import EvidenceStore
from Runtime.ReferenceImplementation.authority import (
    ApprovalDecisionResolver,
    RuntimeBudgetLedger,
    SubAgentTaskPlanner,
    SurfaceGrantProjector,
    TaskContractIssuer,
)
from Runtime.ReferenceImplementation.canonicalization import sha256_jcs
from Runtime.ReferenceImplementation.contracts import (
    ApprovalDecision,
    EvidenceRecord,
    ProviderResult,
    TypedAction,
)
from Runtime.ReferenceImplementation.profiles import SubAgentProfile
from Runtime.ReferenceImplementation.runtime import (
    append_reference_evidence,
    EvidenceCompletionGate,
    ProviderPostConditionVerifier,
    RuntimeDispatchGate,
)


def _profile() -> SubAgentProfile:
    """A second profile proves the canonical classes do not depend on Artist data."""
    return SubAgentProfile(
        profile_id="example_review_cli",
        display_name="ExampleReviewCLI",
        provider_id="example_review_provider",
        audience="example_review",
        goal_type="example.asset.review",
        capabilities=("example.asset.inspect", "example.asset.review"),
        primary_capability="example.asset.review",
        required_evidence=("state_observation", "review_capture"),
        scope={
            "default_target_guid": "asset-guid-001",
            "component_type": "Example.Component",
            "property_paths": ["Example.value"],
            "mutation_channels": ["typed_property"],
            "max_targets": 1,
        },
        value={"type": "float", "unit": "normalized", "minimum": 0.0, "maximum": 100.0, "maximum_exclusive": True},
        approval={"default_minimum": 10.0, "default_maximum": 90.0, "minimum_exclusive": True, "maximum_exclusive": True},
        evidence={"source_type": "example_review", "producer": "UnityAgent.ExampleReview.v1", "provenance_token": "example_review_provider"},
    )


def _budgets() -> dict[str, int]:
    return {
        "max_parent_total_calls": 2, "max_parent_reentries": 0, "max_global_replans": 0, "max_escalations": 0,
        "max_child_llm_calls": 1, "max_tool_calls": 10, "max_wall_clock_ms": 120000, "max_child_wall_clock_ms": 60000,
        "max_child_input_tokens": 1000, "max_child_output_tokens": 1000, "max_parent_input_tokens": 1000,
        "max_parent_output_tokens": 1000, "max_process_restarts": 1, "max_provider_retries": 1,
    }


def _fixture() -> tuple[SubAgentProfile, object, ApprovalDecision, object, TypedAction]:
    profile = _profile()
    project = {"root": str(Path("D:/ProjectAI")), "name": "generic-contract-test"}
    task = TaskContractIssuer().issue(
        task_id="generic-task",
        run_id="generic-run",
        project=project,
        project_fingerprint=sha256_jcs(project),
        budgets=_budgets(),
        issued_at=datetime.now(timezone.utc).isoformat(),
        profile=profile,
    )
    approval = ApprovalDecision.approve(
        approval_decision_id="generic-approval",
        task=task,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        profile=profile,
    )
    grant = SurfaceGrantProjector().derive(
        task=task,
        approval=approval,
        subagent_instance_id="generic-instance",
        profile=profile,
    )
    action = TypedAction.propose(
        action_id="generic-action",
        idempotency_key="generic-idempotency",
        task=task,
        approval=approval,
        grant=grant,
        value=42.0,
        expected_revision="generic-before",
        profile=profile,
    )
    return profile, task, approval, grant, action


def _result(action: TypedAction, profile: SubAgentProfile, *, after: float = 42.0, revision: str = "generic-after") -> ProviderResult:
    value = {
        "schema_version": "1.1",
        "status": "passed",
        "provider_ref": profile.provider_id,
        "action_id": action.action_id,
        "project": dict(action.project),
        "target": dict(action.target),
        "property_path": action.property_path,
        "before_value": 40.0,
        "after_value": after,
        "observed_revision": revision,
        "exact_diff": {"target": action.target["guid"], "property": action.property_path, "before": 40.0, "after": after},
        "evidence": list(profile.required_evidence),
        "mutation_count": 1,
        "boundary_violations": [],
        "failure_class": None,
        "provider_result_digest": "",
    }
    value["provider_result_digest"] = sha256_jcs({key: item for key, item in value.items() if key != "provider_result_digest"})
    return ProviderResult.from_dict(value)


class _MemoryEvidenceStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}

    def add(self, evidence_id: str, task: object, action: TypedAction, evidence_type: str) -> None:
        self.records[evidence_id] = {
            "verification_status": "passed",
            "observation_state": "observed",
            "durability": "durable",
            "source_ref": evidence_type,
            "run_id": task.run_id,
            "mutation_provenance": {"action_id": action.action_id, "action_digest": action.action_digest},
        }

    def get(self, evidence_id: str) -> dict[str, object]:
        return self.records[evidence_id]


def _durable_writer(store: EvidenceStore, task, approval, grant, profile: SubAgentProfile):
    def write(action: TypedAction, result: ProviderResult) -> list[str]:
        ids: list[str] = []
        for evidence_type in profile.required_evidence:
            evidence_id = f"{action.run_id}-{action.action_id}-{evidence_type}"
            record = EvidenceRecord.observed(
                evidence_id=evidence_id,
                task_id=task.task_id,
                run_id=task.run_id,
                action_id=action.action_id,
                evidence_type=evidence_type,
                payload={"observed": True, "value": result.after_value},
                profile=profile,
            )
            append_reference_evidence(
                store=store,
                task=task,
                action=action,
                result=result,
                evidence=record,
                evidence_type=evidence_type,
                profile=profile,
                approval=approval,
                grant=grant,
            )
            ids.append(evidence_id)
        return ids
    return write


class GenericSubAgentContractTests(unittest.TestCase):
    def test_profile_drives_all_canonical_contracts_and_planning(self) -> None:
        profile, task, approval, grant, action = _fixture()
        self.assertEqual(task.goal_type, profile.goal_type)
        self.assertEqual(approval.capability, profile.primary_capability)
        self.assertEqual(grant.audience, profile.audience)
        self.assertEqual(action.target["component_type"], profile.scope["component_type"])
        self.assertEqual(action.property_path, profile.action_property_path)
        plan = SubAgentTaskPlanner().plan(task, RuntimeBudgetLedger(task.budgets), profile=profile)
        self.assertEqual(plan["subagent_profile_id"], profile.profile_id)
        self.assertEqual(plan["provider_id"], profile.provider_id)

    def test_full_idempotency_namespace_allows_isolated_runs_but_rejects_claim_reuse(self) -> None:
        profile, task, approval, grant, action = _fixture()
        result = _result(action, profile)
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(directory)
            writer = _durable_writer(store, task, approval, grant, profile)
            ledger = RuntimeDispatchGate(profile=profile, evidence_store=store)
            ledger.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=lambda _: result, evidence_writer=writer)
            isolated_task = replace(task, run_id="generic-run-2")
            # The digest is deliberately recomputed because run_id is part of the contract binding.
            task_data = isolated_task.to_dict()
            task_data["contract_digest"] = sha256_jcs({key: value for key, value in task_data.items() if key != "contract_digest"})
            isolated_task = type(task).from_dict(task_data, profile=profile)
            isolated_approval = ApprovalDecision.approve(
                approval_decision_id="generic-approval-2",
                task=isolated_task,
                expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                profile=profile,
            )
            isolated_grant = SurfaceGrantProjector().derive(task=isolated_task, approval=isolated_approval, subagent_instance_id="generic-instance-2", profile=profile)
            isolated_action = TypedAction.propose(
                action_id="generic-action-2",
                idempotency_key=action.idempotency_key,
                task=isolated_task,
                approval=isolated_approval,
                grant=isolated_grant,
                value=42.0,
                expected_revision="generic-before",
                profile=profile,
            )
            self.assertNotEqual(ledger.idempotency._namespace(action), ledger.idempotency._namespace(isolated_action))
            with self.assertRaises(Exception):
                reused = TypedAction.propose(
                    action_id="generic-action-reused",
                    idempotency_key=action.idempotency_key,
                    task=task,
                    approval=approval,
                    grant=grant,
                    value=43.0,
                    expected_revision="generic-before",
                    profile=profile,
                )
                ledger.dispatch(task=task, approval=approval, grant=grant, action=reused, dispatch_provider=lambda _: result, evidence_writer=writer)

    def test_postcondition_is_fail_closed_and_completion_supports_multiple_actions(self) -> None:
        profile, task, approval, grant, action = _fixture()
        result = _result(action, profile)
        with self.assertRaises(Exception):
            ProviderPostConditionVerifier(profile=profile).verify(action=action, result=replace(result, observed_revision=""), before_revision=action.expected_revision)

        second = TypedAction.propose(
            action_id="generic-action-2",
            idempotency_key="generic-idempotency-2",
            task=task,
            approval=approval,
            grant=grant,
            value=43.0,
            expected_revision="generic-before",
            profile=profile,
        )
        second_result = _result(second, profile, after=43.0)
        with tempfile.TemporaryDirectory() as directory:
            evidence_store = EvidenceStore(directory)
            gate = RuntimeDispatchGate(profile=profile, evidence_store=evidence_store)
            write_evidence = _durable_writer(evidence_store, task, approval, grant, profile)
            first_dispatch = gate.dispatch(task=task, approval=approval, grant=grant, action=action, dispatch_provider=lambda _: result, evidence_writer=write_evidence)
            second_dispatch = gate.dispatch(task=task, approval=approval, grant=grant, action=second, dispatch_provider=lambda _: second_result, evidence_writer=write_evidence)
            completion = EvidenceCompletionGate(evidence_store, profile=profile).evaluate(
                task=task,
                approval=approval,
                grant=grant,
                actions=[action, second],
                provider_results=[result, second_result],
                reservations=gate.reservations,
                evidence_ids=list(first_dispatch["evidence_ids"]) + list(second_dispatch["evidence_ids"]),
                final_revision="generic-after",
                ledger=RuntimeBudgetLedger(task.budgets),
                profile=profile,
            )
            self.assertEqual(completion.state, "eligible")


if __name__ == "__main__":
    unittest.main()
