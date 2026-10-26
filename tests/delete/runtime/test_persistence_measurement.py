import tempfile
from pathlib import Path
import unittest


class PersistenceMeasurementTests(unittest.TestCase):
    def test_only_new_snapshots_count_bytes_and_failed_telemetry_does_not_undo_writes(self):
        from unityagent.persistence.store.measurement import capture
        from unityagent.persistence.store.atomic_store import write_immutable_json, read_json
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'snapshots/context/one.json'
            events = []
            with capture(lambda *event: events.append(event)):
                write_immutable_json(path, {'text': '日本語'})
                write_immutable_json(path, {'text': '日本語'})
            self.assertEqual([event[1] for event in events if event[0] == 'snapshot.bytes'], [path.stat().st_size])
            def unavailable(*_):
                raise OSError('telemetry unavailable')
            with capture(unavailable):
                write_immutable_json(path.parent / 'two.json', {'text': 'retained'})
            self.assertEqual(read_json(path.parent / 'two.json')['text'], 'retained')

    def test_capture_is_local_and_reports_real_repeated_reads(self):
        from unityagent.persistence.store.measurement import capture, observed
        calls, events = [], []
        @observed('evidence.verify')
        def verify():
            calls.append(1)
            return 'verified'
        with capture(lambda *event: events.append(event)):
            verify()
            verify()
        verify()
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(event[1] >= 0 for event in events))
