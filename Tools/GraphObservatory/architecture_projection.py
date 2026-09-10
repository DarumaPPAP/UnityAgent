"""Human-facing UnityAgent architecture projection.

This module intentionally projects a small mental model over the canonical
repository. It is a read-only navigation aid, not a second architecture or
routing authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


CONCEPTS: tuple[dict[str, Any], ...] = (
    {
        "id": "rules",
        "label": "Rules",
        "question": "やっていい？",
        "summary": "安全境界・ユーザー方針・承認条件を確認する。",
        "description": "Policyが、変更可能範囲・承認・Evidence要求などの境界を定義します。",
        "machine_areas": ["Policy/"],
        "source_paths": [
            "Policy/User/user-policy.yaml",
            "Policy/",
        ],
    },
    {
        "id": "planner",
        "label": "Planner",
        "question": "どう進める？",
        "summary": "Taskを分類し、必要な手順だけを組み立てる。",
        "description": "OrchestrationがTask Routingを担当します。単純な仕事はFast Path、複雑な仕事だけGraph / Loopを使います。",
        "machine_areas": ["Orchestration/", "Graph / Loop (conditional)"],
        "source_paths": [
            "Orchestration/Routing/task-routes.yaml",
            "docs/architecture/architecture.md",
        ],
    },
    {
        "id": "knowledge",
        "label": "Knowledge",
        "question": "何を読む？",
        "summary": "必要なContext・Skill・外部Knowledgeだけを選ぶ。",
        "description": "Context SelectionとSkillsがTaskへ必要な情報を絞り込みます。MyResourceCenterはReference Snapshot経由の外部Knowledgeとして接続します。",
        "machine_areas": ["Context/", ".agents/skills/", "MyResourceCenter Snapshot"],
        "source_paths": [
            "Context/Selection/context-catalog.yaml",
            "Context/Retrieval/Reference/reference-navigator.yaml",
            ".agents/skills/",
            "docs/architecture/local-reference-navigator.md",
        ],
    },
    {
        "id": "executor",
        "label": "Executor",
        "question": "何を実行する？",
        "summary": "Capabilityを安全に解決し、Unity・Code・Toolを操作する。",
        "description": "RuntimeがProvider製品名ではなくCapabilityを起点に、Guard・Resolver・Dispatcherを通して実行します。",
        "machine_areas": ["Runtime/", "Provider / Harness"],
        "source_paths": [
            "Runtime/Tooling/tool_broker.py",
            "Runtime/Dispatcher/tool_runtime_dispatcher.py",
            "Runtime/Guardrails/tool_runtime_guard.py",
            "docs/architecture/production-tool-runtime.md",
        ],
    },
    {
        "id": "evidence",
        "label": "Evidence",
        "question": "本当に起きた？",
        "summary": "成功したつもりではなく、観測結果を構造化する。",
        "description": "Compile / Editor / Player / Performanceなどを混同せず、ProviderResultをcanonical Evidenceへ正規化します。",
        "machine_areas": ["Runtime/EvidenceCapture/"],
        "source_paths": [
            "Runtime/EvidenceCapture/provider_evidence.py",
            "Runtime/Contracts/",
        ],
    },
    {
        "id": "memory",
        "label": "Memory",
        "question": "何を残す？",
        "summary": "再利用すべきState・Checkpoint・Evidenceだけを永続化する。",
        "description": "Persistenceがdurable stateの所有者です。Runtimeの観測結果はappend/read-backされて初めて永続Evidenceになります。",
        "machine_areas": ["Persistence/"],
        "source_paths": [
            "Persistence/",
            "docs/architecture/architecture.md",
        ],
    },
    {
        "id": "quality",
        "label": "Quality",
        "question": "悪化してない？",
        "summary": "Behavior Regressionと品質変化をBaselineと比較する。",
        "description": "Evalが観測済みEvidenceを評価し、RegressionやRebaseline必要性を判定します。Operationsは実行状態の観測・制御を支えます。",
        "machine_areas": ["Eval/", "Operations/"],
        "source_paths": [
            "Eval/",
            "Operations/",
            "Tools/run_regression_gate.py",
        ],
    },
)


TOUR: tuple[dict[str, str], ...] = (
    {
        "id": "intro",
        "concept_id": "",
        "label": "UnityAgent",
        "caption": "UnityAgentは、Unity開発を『考える → 実行する → 検証する』ためのAgent基盤です。最初から内部ファイルを全部覚える必要はありません。",
    },
    {
        "id": "rules",
        "concept_id": "rules",
        "label": "1. Rules",
        "caption": "最初に境界を確認します。ユーザー方針、変更Scope、承認、必要Evidenceをここで決めます。",
    },
    {
        "id": "planner",
        "concept_id": "planner",
        "label": "2. Planner",
        "caption": "次に進め方を決めます。小さいTaskはFast Path、複数判断が必要なときだけGraphやLoopへ展開します。",
    },
    {
        "id": "knowledge",
        "concept_id": "knowledge",
        "label": "3. Knowledge",
        "caption": "必要なContextとSkillだけを選びます。MyResourceCenterはUnityAgent内部に抱えず、Reference Snapshotとして必要時に参照します。",
    },
    {
        "id": "executor",
        "concept_id": "executor",
        "label": "4. Executor",
        "caption": "RuntimeがCapabilityを安全に実行します。Unity CLIやMCPは必須ではなく、利用可能なProviderをRuntime側で解決します。",
    },
    {
        "id": "evidence",
        "concept_id": "evidence",
        "label": "5. Evidence",
        "caption": "実行しただけでは成功扱いしません。Compile、Editor、Player、Profilerなど、実際に観測した結果を分離して記録します。",
    },
    {
        "id": "memory",
        "concept_id": "memory",
        "label": "6. Memory",
        "caption": "再利用価値のあるStateやEvidenceだけをPersistenceへ残します。途中の一時情報を何でも永続化する設計にはしません。",
    },
    {
        "id": "quality",
        "concept_id": "quality",
        "label": "7. Quality",
        "caption": "最後にRegressionを確認します。Candidateが動いたかだけでなく、以前より悪化していないかをEvalで比較します。",
    },
    {
        "id": "outro",
        "concept_id": "",
        "label": "Mental Model",
        "caption": "覚えるのは7つだけです。Rules → Planner → Knowledge → Executor → Evidence → Memory / Quality。内部詳細は必要になったときだけ掘ります。",
    },
)


TASK_DEMO: dict[str, Any] = {
    "title": "Shaderを最適化して",
    "subtitle": "実際の依頼が7つの概念をどう流れるか",
    "steps": [
        {"concept_id": "rules", "label": "Rules", "detail": "変更範囲・対象Platform・必須Evidenceを確認"},
        {"concept_id": "planner", "label": "Planner", "detail": "Rendering / Performance Taskとして作業順を決定"},
        {"concept_id": "knowledge", "label": "Knowledge", "detail": "Shader Skill・Project Fact・Reference Snapshotを選択"},
        {"concept_id": "executor", "label": "Executor", "detail": "Shader Source・Variant・Profiler等をCapability経由で観測 / 修正"},
        {"concept_id": "evidence", "label": "Evidence", "detail": "GPU時間・Variant・Visual結果など観測済みFactを記録"},
        {"concept_id": "quality", "label": "Quality", "detail": "Regressionと期待した改善が両立しているか確認"},
    ],
}


SYSTEM_STACK: tuple[dict[str, str], ...] = (
    {
        "id": "resource-center",
        "label": "MyResourceCenter",
        "question": "What do we know?",
        "summary": "Catalog / Evidence / Reference Snapshotとして外部Knowledgeを提供する。",
    },
    {
        "id": "unity-agent",
        "label": "UnityAgent",
        "question": "What should we do?",
        "summary": "RulesからQualityまでの判断・実行・検証を統括する。",
    },
    {
        "id": "unity-project",
        "label": "Unity Project",
        "question": "What actually happened?",
        "summary": "Code / Scene / Shader / Profiler / Test / Build / Playerの実測対象。",
    },
)


def _validate_source_paths(root: Path, concepts: tuple[dict[str, Any], ...]) -> None:
    missing: list[str] = []
    for concept in concepts:
        for relative in concept["source_paths"]:
            if not (root / relative).exists():
                missing.append(relative)
    if missing:
        joined = ", ".join(sorted(set(missing)))
        raise FileNotFoundError(f"Human architecture projection references missing paths: {joined}")


def build_human_architecture(root: Path) -> dict[str, Any]:
    """Return a validated, read-only human architecture model."""
    _validate_source_paths(root, CONCEPTS)
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "UnityAgent Human Architecture",
        "tagline": "3分で全体像を掴み、必要なときだけ内部へ潜る。",
        "concepts": list(CONCEPTS),
        "tour": list(TOUR),
        "task_demo": TASK_DEMO,
        "system_stack": list(SYSTEM_STACK),
        "principles": [
            "Human MapはMachine Architectureの代替Source of Truthではない",
            "GraphはPlanner内部で必要時だけ使うDerived Strategy",
            "MyResourceCenterはUnityAgentとは独立したKnowledge Library",
            "Visualizerはread-only / offlineを維持しCanonical Contractを書き換えない",
        ],
    }
