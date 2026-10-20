import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import connection_layout_release as release


class CSSPublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ui = self.root/'ui'
        (self.ui/'assets').mkdir(parents=True)
        (self.root/'frontend/dist/assets').mkdir(parents=True)
        self.original = ('<script src="/assets/unchanged.js"></script><link rel="stylesheet" href="'+release.OLD+'">').encode()
        (self.ui/'index.html').write_bytes(self.original)
        (self.ui/release.OLD.lstrip('/')).write_bytes(b'.old{color:red}.other{color:blue}')
        self.css = self.root/'frontend/dist'/release.NEW.lstrip('/')
        self.css.write_bytes(b'.old{color:red}'+b'x'*1021+b'.other{color:blue}')
        self.context = patch.multiple(release, ROOT=self.root, UI=self.ui,
            INDEX_SHA=hashlib.sha256(self.original).hexdigest(), NEW_SHA=release.sha(self.css))
        self.context.start()
        self.addCleanup(self.context.stop)

    def test_only_stylesheet_reference_changes(self):
        body, _ = release.payload()
        self.assertEqual(body.replace(release.NEW.encode(), release.OLD.encode()), self.original)
        self.assertIn(b'/assets/unchanged.js', body)

    def test_rejects_parallel_live_release(self):
        (self.ui/'index.html').write_bytes(self.original+b'changed')
        with self.assertRaises(AssertionError):
            release.payload()

    def test_rejects_unreviewed_build(self):
        self.css.write_bytes(self.css.read_bytes()+b'unrelated')
        with self.assertRaises(AssertionError):
            release.payload()

    def test_rejects_edits_to_existing_css_even_with_updated_digest(self):
        self.css.write_bytes(self.css.read_bytes().replace(b'color:red', b'color:tan'))
        with patch.object(release, 'NEW_SHA', release.sha(self.css)):
            with self.assertRaises(AssertionError):
                release.payload()

    def test_preview_rejects_every_mutating_method(self):
        for method in ('do_POST', 'do_PUT', 'do_PATCH', 'do_DELETE'):
            self.assertIs(getattr(release.Preview, method), release.Preview.deny)


if __name__ == '__main__':
    unittest.main()
