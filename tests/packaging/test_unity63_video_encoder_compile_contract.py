"""Regression for observed Unity 6000.3.12f1 PlayVideoEncoder compiler errors."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Packages/com.darumappap.unity-agent/Editor/PlayVideoEncoder.cs'


class Unity63VideoEncoderCompileContract(unittest.TestCase):
    def test_explicit_unity_editor_type_avoids_cs0118_namespace_collision(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn('typeof(UnityEditor.Editor).Assembly.GetType(', source)
        self.assertNotIn('typeof(Editor).Assembly.GetType(', source)

    def test_unsigned_h264_gop_size_avoids_cs0266(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn('gopSize = (uint)fps,', source)
        self.assertNotIn('gopSize = fps,', source)


if __name__ == '__main__':
    unittest.main()
