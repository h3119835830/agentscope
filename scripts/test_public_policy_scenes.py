"""Offline checks for data collection; does not call a model or upstream tools."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('public_scene_collector', Path(__file__).with_name('collect_public_policy_scenes.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
task_inputs = collector.task_inputs


class PublicSceneCollectionTests(unittest.TestCase):
    def test_excludes_answers_not_referenced_by_task(self):
        _, parts = task_inputs('class T:\n _FILENAME = "answer"\n PROMPT = "Find largest file"\n GROUND_TRUTH_OUTPUT = _FILENAME\n', 'T', 'PROMPT')
        self.assertEqual(parts, ['PROMPT = "Find largest file"'])

    def test_preserves_task_input_dependencies(self):
        _, parts = task_inputs('class T:\n _ID = "13"\n GOAL = f"Delete {_ID}"\n GROUND_TRUTH_OUTPUT = "no"\n', 'T', 'GOAL')
        self.assertEqual(len(parts), 2)
        self.assertIn('_ID = "13"', parts)

    def test_transitive_and_annotated_dependencies(self):
        _, parts = task_inputs('class T:\n A: str = "13"\n B = A\n GOAL = f"Delete {B}"\n', 'T', 'GOAL')
        self.assertEqual(len(parts), 3)

    def test_does_not_execute_upstream_code(self):
        _, parts = task_inputs('raise RuntimeError("do not execute")\nclass T:\n PROMPT = "read"\n def utility(self):\n  raise RuntimeError("never")\n', 'T', 'PROMPT')
        self.assertEqual(parts, ['PROMPT = "read"'])

    def test_missing_task_input_is_rejected(self):
        with self.assertRaises(ValueError):
            task_inputs('class T:\n ANSWER = "x"\n', 'T', 'PROMPT')

    def test_frozen_scene_hashes_match_files(self):
        root = Path(__file__).resolve().parents[1] / 'acceptance/public-scene-baseline-20261025-v2'
        for case in json.loads((root / 'manifest.json').read_text(encoding='utf-8'))['cases']:
            self.assertEqual(hashlib.sha256((root / 'scenes' / case['id'] / 'scene.md').read_bytes()).hexdigest(), case['scene_sha256'])

    def test_clean_query_has_no_answer_constant(self):
        root = Path(__file__).resolve().parents[1] / 'acceptance/public-scene-baseline-20261025-v2'
        text = (root / 'scenes/dojo-normal-query-clean/scene.md').read_text(encoding='utf-8')
        self.assertNotIn('recipe-collection', text)
        self.assertNotIn('GROUND_TRUTH', text)
        self.assertNotIn('_FILENAME', text)


if __name__ == '__main__':
    unittest.main()
