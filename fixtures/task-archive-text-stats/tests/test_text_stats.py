import unittest
from backend.text_stats import word_count
class WordCountTests(unittest.TestCase):
    def test_multiple_spaces(self):
        self.assertEqual(word_count('hello   world'), 2)
    def test_tabs_and_empty(self):
        self.assertEqual(word_count('hello\tworld'), 2)
        self.assertEqual(word_count(''), 0)
