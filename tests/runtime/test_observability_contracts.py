"""観測失敗の隔離、秘匿性、永続化、実測Usageの既存正本。

旧10件との不変条件比較を完了し、元BlobはGit履歴で保持する。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from unityagent.control_plane.measurement import measured, record_model_usage
from unityagent.persistence.store.atomic_store import read_json, write_immutable_json
from unityagent.persistence.store.measurement import capture, observed
from unityagent.runtime.telemetry.model_usage import observe_codex_usage


class MeasurementBoundaryTests(unittest.TestCase):
    @staticmethod
    def plane(root: str) -> SimpleNamespace:
        layout = SimpleNamespace(root=Path(root))
        return SimpleNamespace(state_store=SimpleNamespace(layout=layout))

    def test_metric_failure_does_not_replay_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            mutations = []
            with patch(
                "unityagent.control_plane.measurement.OperationalEventStore",
                side_effect=OSError("disk full"),
            ):
                with measured(self.plane(directory), "run", "provider"):
                    mutations.append("executed")
            self.assertEqual(mutations, ["executed"])

    def test_source_exception_is_preserved_and_private_message_is_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            failure = ValueError("private source prompt")
            with self.assertRaises(ValueError) as raised:
                with measured(self.plane(directory), "run", "provider"):
                    raise failure
            self.assertIs(raised.exception, failure)
            text = (Path(directory) / "operations/metric.jsonl").read_text(encoding="utf-8")
            self.assertIn("duration", text)
            self.assertNotIn("private", text)

    def test_metrics_and_usage_projections_retain_only_structured_values(self):
        with tempfile.TemporaryDirectory() as directory:
            plane = self.plane(directory)
            with measured(plane, "run", "context") as counters:
                counters.update(
                    selected_utf8_bytes=123,
                    estimated_tokens=31,
                    input_tokens=None,
                    prompt="private source",
                )
            metrics = (Path(directory) / "operations/metric.jsonl").read_text(encoding="utf-8")
            self.assertIn("selected_utf8_bytes", metrics)
            self.assertNotIn("input_tokens", metrics)
            self.assertNotIn("private", metrics)

            record_model_usage(
                plane,
                "run",
                {
                    "input_tokens": None,
                    "output_tokens": None,
                    "configured_model": "configured-model",
                    "model_revision": None,
                    "scope": "all_observed_completed_turns",
                    "unit": "tokens",
                    "prompt": "private source",
                },
            )
            trace = (Path(directory) / "operations/trace.jsonl").read_text(encoding="utf-8")
            self.assertIn('"input_tokens":null', trace)
            self.assertNotIn("private", trace)

    def test_immutable_writes_survive_telemetry_failure_and_count_only_new_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots/context/one.json"
            events = []
            with capture(lambda *event: events.append(event)):
                write_immutable_json(path, {"text": "日本語"})
                write_immutable_json(path, {"text": "日本語"})
            self.assertEqual(
                [event[1] for event in events if event[0] == "snapshot.bytes"],
                [path.stat().st_size],
            )

            def unavailable(*_args):
                raise OSError("telemetry unavailable")

            with capture(unavailable):
                write_immutable_json(path.parent / "two.json", {"text": "retained"})
            self.assertEqual(read_json(path.parent / "two.json")["text"], "retained")

    def test_observation_counts_real_reads_only_within_capture_scope(self):
        calls, events = [], []

        @observed("evidence.verify")
        def verify():
            calls.append(1)
            return "verified"

        with capture(lambda *event: events.append(event)):
            self.assertEqual(verify(), "verified")
            self.assertEqual(verify(), "verified")
        verify()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event[1] >= 0 for event in events))


class ModelUsageBoundaryTests(unittest.TestCase):
    @staticmethod
    def observe(events: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(
                "\n".join(json.dumps(event) for event in events),
                encoding="utf-8",
            )
            return observe_codex_usage(
                path, model="configured-model", reasoning_effort="high"
            )

    def test_missing_observation_does_not_invent_usage_or_copy_source_text(self):
        result = self.observe([{"type": "item.completed", "text": "private source prompt"}])
        self.assertIsNone(result["input_tokens"])
        self.assertIsNone(result["output_tokens"])
        self.assertIsNone(result["model_revision"])
        self.assertNotIn("private", json.dumps(result))

    def test_completed_turns_are_aggregated_without_double_counting_cached_tokens(self):
        result = self.observe([
            {"type": "turn.completed", "usage": {
                "input_tokens": 20, "cached_input_tokens": 10, "output_tokens": 3,
            }},
            {"type": "turn.completed", "usage": {
                "input_tokens": 5, "cached_input_tokens": 2, "output_tokens": 4,
            }},
        ])
        self.assertEqual(result["input_tokens"], 25)
        self.assertEqual(result["cached_input_tokens"], 12)
        self.assertEqual(result["output_tokens"], 7)
        self.assertEqual(result["completed_turns"], 2)
        self.assertEqual(result["usage_source"], "codex.turn.completed.usage")

    def test_invalid_usage_fails_closed_but_missing_cache_remains_unknown(self):
        for usage in (
            {"input_tokens": True, "output_tokens": 2},
            {"input_tokens": -1, "output_tokens": 2},
            {"input_tokens": 2, "cached_input_tokens": 3, "output_tokens": 2},
            {"input_tokens": 2},
        ):
            with self.subTest(usage=usage):
                result = self.observe([{"type": "turn.completed", "usage": usage}])
                self.assertIsNone(result["input_tokens"])
                self.assertIsNone(result["output_tokens"])
        result = self.observe([{"type": "turn.completed", "usage": {
            "input_tokens": 20, "output_tokens": 3,
        }}])
        self.assertEqual(result["input_tokens"], 20)
        self.assertIsNone(result["cached_input_tokens"])


if __name__ == "__main__":
    unittest.main()
