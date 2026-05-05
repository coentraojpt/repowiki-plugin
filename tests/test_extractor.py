import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import unittest
from pathlib import Path

from extractor import _md5, _load_cache, _save_cache


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_md5_deterministic(self):
        f = self.dir / "file.py"
        f.write_text("hello")
        self.assertEqual(_md5(f), _md5(f))
        self.assertEqual(len(_md5(f)), 8)

    def test_md5_changes_on_content_change(self):
        f = self.dir / "file.py"
        f.write_text("hello")
        h1 = _md5(f)
        f.write_text("world")
        self.assertNotEqual(h1, _md5(f))

    def test_md5_missing_file_returns_fallback(self):
        result = _md5(self.dir / "nonexistent.py")
        self.assertEqual(result, "00000000")

    def test_load_cache_missing_returns_empty(self):
        cache = _load_cache(self.dir / "nonexistent.json")
        self.assertEqual(cache["version"], 1)
        self.assertEqual(cache["entries"], {})

    def test_load_cache_wrong_version_returns_empty(self):
        p = self.dir / "cache.json"
        p.write_text(json.dumps({"version": 99, "entries": {"x": "y"}}))
        cache = _load_cache(p)
        self.assertEqual(cache["entries"], {})

    def test_save_load_roundtrip(self):
        p = self.dir / "cache.json"
        data = {
            "version": 1,
            "entries": {"apps/models.py": {"hash": "abcd1234", "shallow": "# models.py"}},
        }
        _save_cache(p, data)
        loaded = _load_cache(p)
        self.assertEqual(loaded["entries"]["apps/models.py"]["shallow"], "# models.py")


if __name__ == "__main__":
    unittest.main()
