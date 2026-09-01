"""Capability-local MyUnityMCP tool materialization.

Only tool names needed by the requested capability are returned. The adapter
never materializes the full MyUnityMCP tool catalog into Context.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    group: str | None = None
    input_schema: Mapping[str, object] | None = None


@dataclass(frozen=True)
class MutationWorkflow:
    key: str
    prepare_tool: str
    apply_tool: str
    approval_group: str


READ_CAPABILITY_TOOLS: dict[str, tuple[str, ...]] = {
    "project.inspect": ("graphics.inspect_project",),
    "scene.inspect": ("graphics.inspect_scene", "graphics.validate_scene"),
    "profiler.observe": (
        "profiler.inspect_environment",
        "profiler.inspect_counters",
        "profiler.summarize_capture",
    ),
    "visual.capture": ("graphics.capture_evidence",),
}

AGENT_WORKFLOW_TOOLS: tuple[str, ...] = (
    "agent.inspect_capabilities",
    "agent.validate_workflow",
    "agent.compile_graph",
    "agent.preview_execution",
    "agent.submit_approval",
    "agent.start_execution",
    "agent.get_execution_status",
)

MUTATION_WORKFLOWS: dict[str, MutationWorkflow] = {
    "graphics.light": MutationWorkflow(
        "graphics.light",
        "graphics.prepare_light_plan",
        "graphics.apply_plan",
        "mutate",
    ),
    "graphics.environment": MutationWorkflow(
        "graphics.environment",
        "graphics.prepare_environment_plan",
        "graphics.apply_environment_plan",
        "mutate",
    ),
    "ui.rect_transform": MutationWorkflow(
        "ui.rect_transform",
        "ui.prepare_rect_transform",
        "ui.apply_rect_transform",
        "ui",
    ),
    "animation.parameter": MutationWorkflow(
        "animation.parameter",
        "animation.prepare_parameter",
        "animation.apply_parameter",
        "animation",
    ),
    "audio.source": MutationWorkflow(
        "audio.source",
        "audio.prepare_source",
        "audio.apply_source",
        "audio",
    ),
    "cinematic.director": MutationWorkflow(
        "cinematic.director",
        "cinematic.prepare_director",
        "cinematic.apply_director",
        "cinematic",
    ),
    "addressables.entry": MutationWorkflow(
        "addressables.entry",
        "addressables.prepare_entry",
        "addressables.apply_entry",
        "addressables",
    ),
}

# Save and Bake are intentionally not scene.mutate workflows. Their separate
# approval boundaries must remain explicit.
SEPARATE_APPROVAL_TOOLS = frozenset(
    {
        "graphics.prepare_save_plan",
        "graphics.apply_save_plan",
        "graphics.prepare_bake_plan",
        "graphics.bake_dependencies",
        "graphics.prepare_apv_bake_plan",
        "graphics.start_apv_bake",
    }
)


def _by_name(discovered_tools: Iterable[ToolDescriptor]) -> dict[str, ToolDescriptor]:
    return {tool.name: tool for tool in discovered_tools}


def materialize_capability_tools(
    capability: str,
    discovered_tools: Iterable[ToolDescriptor],
    *,
    workflow_key: str | None = None,
) -> tuple[ToolDescriptor, ...]:
    """Return only live, enabled tool descriptors needed by one capability."""
    available = _by_name(discovered_tools)

    if capability in READ_CAPABILITY_TOOLS:
        names = READ_CAPABILITY_TOOLS[capability]
    elif capability == "scene.mutate":
        if not workflow_key or workflow_key not in MUTATION_WORKFLOWS:
            return ()
        workflow = MUTATION_WORKFLOWS[workflow_key]
        names = (workflow.prepare_tool, workflow.apply_tool)
    elif capability == "domain.workflow":
        names = AGENT_WORKFLOW_TOOLS
    else:
        return ()

    if any(name not in available for name in names):
        return ()
    return tuple(available[name] for name in names)


def available_capabilities(
    discovered_tools: Iterable[ToolDescriptor],
) -> frozenset[str]:
    """Compute executable capabilities without claiming future registry surfaces."""
    available = _by_name(discovered_tools)
    capabilities = {
        capability
        for capability, names in READ_CAPABILITY_TOOLS.items()
        if all(name in available for name in names)
    }
    if any(
        workflow.prepare_tool in available and workflow.apply_tool in available
        for workflow in MUTATION_WORKFLOWS.values()
    ):
        capabilities.add("scene.mutate")
    if all(name in available for name in AGENT_WORKFLOW_TOOLS):
        capabilities.add("domain.workflow")
    return frozenset(capabilities)


def mutation_workflow(workflow_key: str) -> MutationWorkflow:
    try:
        return MUTATION_WORKFLOWS[workflow_key]
    except KeyError as exc:
        raise ValueError(f"unsupported MyUnityMCP mutation workflow: {workflow_key}") from exc
