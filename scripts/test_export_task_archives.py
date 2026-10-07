import unittest
from collections import Counter
from export_task_archives import all_events, assert_public, record_filename, scrub


class ArchiveExportTests(unittest.TestCase):
    def test_public_policy_survives_while_private_material_is_removed(self):
        counts = Counter()
        result = scrub({"task_id": "legacy-demo", "statement": "Protect tests; write output only after approval",
                        "secret": "do-not-publish", "excerpt": "unreviewed source text",
                        "events": [{"type": "thinking", "text": "private stream"}],
                        "diagnostic": "api_key=example-private-value Bearer opaque-private-value"}, counts)
        self.assertEqual(result["statement"], "Protect tests; write output only after approval")
        self.assertNotIn("secret", result)
        self.assertNotIn("excerpt", result)
        self.assertEqual(result["events"], [{"redacted": True}])
        self.assertNotIn("example-private-value", result["diagnostic"])
        self.assertNotIn("opaque-private-value", result["diagnostic"])
        assert_public(result)

    def test_legacy_and_untrusted_ids_cannot_escape_record_directory(self):
        self.assertEqual(record_filename("legacy-demo-task"), "legacy-demo-task.json")
        self.assertEqual(record_filename("a" * 32), "a" * 32 + ".json")
        self.assertRegex(record_filename("../../private"), r"^id-[a-f0-9]{64}\.json$")

    def test_every_page_is_exported_and_cross_task_rows_are_rejected(self):
        class Projection:
            @staticmethod
            def page(connection, task, category, before, limit, with_detail):
                return {"events": [{"id": "event-2" if before else "event-1", "task_id": task, "category": category}],
                        "total": 2, "next_cursor": None if before else "older"}
        self.assertEqual([r["id"] for r in all_events(Projection, None, "task", "tools")], ["event-1", "event-2"])

        class BadProjection:
            @staticmethod
            def page(*args, **kwargs):
                return {"events": [{"id": "event-1", "task_id": "other", "category": "tools"}], "total": 1, "next_cursor": None}
        with self.assertRaisesRegex(AssertionError, "Cross-task"):
            all_events(BadProjection, None, "task", "tools")

    def test_truncated_export_is_rejected(self):
        class Projection:
            @staticmethod
            def page(*args, **kwargs):
                return {"events": [], "total": 10, "next_cursor": None}
        with self.assertRaisesRegex(AssertionError, "truncated"):
            all_events(Projection, None, "task", "kernel")


if __name__ == "__main__":
    unittest.main()
