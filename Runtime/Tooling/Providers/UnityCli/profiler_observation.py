"""Unity Pipeline の read-only 性能Snapshotを計測条件付きEvidenceへ変換する。"""
from __future__ import annotations

import math
import platform
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "Contracts" / "profiler-observation.schema.json"


class ProfilerObservationError(ValueError):
    pass


def _counter(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ProfilerObservationError(f"{name} is not a finite non-negative measurement")
    try:
        measured = float(value)
    except OverflowError as exc:
        raise ProfilerObservationError(f"{name} exceeds the supported numeric range") from exc
    if not math.isfinite(measured):
        raise ProfilerObservationError(f"{name} is not a finite non-negative measurement")
    return measured


def _payload(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfilerObservationError("Unity Pipeline did not return structured performance data")
    result = value.get("result", value)
    if not isinstance(result, Mapping) or any(not isinstance(result.get(key), Mapping) for key in ("render", "memory", "frameTiming")):
        raise ProfilerObservationError("Unity Pipeline performance result is incomplete")
    return result


def normalize_profiler_observation(value: Any, *, unity_version: str, observed_at: datetime | None = None) -> dict[str, Any]:
    """一時点のEditor値をTarget Deviceの測定値へ昇格させず正規化する。"""
    source = _payload(value)
    memory = source["memory"]
    render = source["render"]
    timing = source["frameTiming"]
    if not isinstance(timing.get("available"), bool):
        raise ProfilerObservationError("frame timing availability is not observed")

    metrics = []
    memory_counters = (
        ("totalAllocatedBytes", "Unity Total Allocated", "memory"),
        ("totalReservedBytes", "Unity Total Reserved", "memory"),
        ("monoUsedBytes", "Mono Used", "memory"),
        ("monoHeapBytes", "Mono Heap", "memory"),
    )
    for key, name, category in memory_counters:
        measured = _counter(memory.get(key), key)
        metrics.append({"name": name, "value": measured, "unit": "bytes", "category": category})
    if not any(item["value"] > 0 for item in metrics):
        raise ProfilerObservationError("Unity Pipeline returned no usable memory measurement")

    if timing["available"]:
        for key, name, category in (("cpuFrameTimeMs", "CPU Frame Time", "cpu"), ("cpuMainThreadFrameTimeMs", "CPU Main Thread Frame Time", "cpu"), ("gpuFrameTimeMs", "GPU Frame Time", "gpu")):
            measured = _counter(timing.get(key), key)
            if measured > 0:
                metrics.append({"name": name, "value": measured, "unit": "ms", "category": category})

    render_counters = {}
    for key in ("drawCalls", "batches", "setPassCalls", "triangles", "vertices"):
        measured = _counter(render.get(key), key)
        if not measured.is_integer():
            raise ProfilerObservationError(f"{key} must be an integer counter")
        render_counters[key] = int(measured)

    timestamp = observed_at or datetime.now(timezone.utc)
    limitations = [
        "Editorの直近1フレームとEditorプロセスのメモリであり、PlayerやTarget Deviceの性能を示さない",
        "Scene/Game ViewとGraphics APIをこのCommandだけでは特定できない",
        "単一SnapshotからボトルネックやBefore/After改善を断定できない",
    ]
    if not timing["available"]:
        limitations.append("CPU/GPU FrameTimingは利用不可。0msの計測値として扱わない")
    metadata = {
        "measurement_source": "unity_pipeline.get_performance_stats",
        "unity_version": unity_version,
        "platform": platform.system() + " Editor",
        "graphics_api": "unknown",
        "capture_mode": "editor_snapshot",
        "build_type": "Editor",
        "scene_or_scope": "last_rendered_editor_frame_scope_unknown",
        "measurement_window": "single_snapshot_of_last_rendered_frame",
        "known_limitations": limitations,
        "validity": "limited",
    }
    observation = {
        "measurement_source": metadata["measurement_source"],
        "platform": metadata["platform"],
        "unity_version": metadata["unity_version"],
        "graphics_api": metadata["graphics_api"],
        "build_type": metadata["build_type"],
        "capture_mode": metadata["capture_mode"],
        "capture_scope": metadata["scene_or_scope"],
        "measurement_window": metadata["measurement_window"],
        "observed_at": timestamp.astimezone(timezone.utc).isoformat(),
        "sample_count": 1,
        "counter_names": [item["name"] for item in metrics],
        "counter_units": {item["name"]: item["unit"] for item in metrics},
        "render_counters": render_counters,
        "known_limitations": limitations,
        "validity": "limited",
        "measurements": [{"capture_id": uuid4().hex, "metadata": metadata, "metrics": metrics}],
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for error in Draft202012Validator(schema).iter_errors(observation):
        raise ProfilerObservationError(f"Profiler observation violates its output contract: {error.message}")
    return observation
