import unittest

from RAG.Query.extract_filters import extract_filters


class FilterExtractionTests(unittest.TestCase):
    def test_only_explicit_unity_pipeline_and_platform_facts_are_extracted(self):
        filters = extract_filters("Unity 6000.3.12f1 URP 17+ Switch rendering")
        self.assertEqual(filters.unity_version, "6000.3.12f1")
        self.assertEqual(filters.render_pipeline, "URP")
        self.assertEqual(filters.pipeline_version, "17+")
        self.assertEqual(filters.platforms, ("Switch",))
        self.assertEqual(filters.domains, ("rendering",))

    def test_unknown_metadata_is_not_invented(self):
        filters = extract_filters("shader issue")
        self.assertIsNone(filters.unity_version)
        self.assertIsNone(filters.render_pipeline)
        self.assertEqual(filters.platforms, ())


if __name__ == "__main__":
    unittest.main()
